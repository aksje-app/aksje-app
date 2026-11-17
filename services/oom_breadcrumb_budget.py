"""Bounded diagnostic history in a fixed namespace of overwrite-only slots."""
from __future__ import annotations

from contextlib import closing, contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from heapq import nlargest
import json
import os
from threading import Lock

_BUDGET_BYTES = 256 * 1024
_SLOT_BYTES = 2 * 1024
_SLOT_COUNT = 15_000  # Leaves room under 32 MiB for keys and metadata.
_RETENTION = timedelta(days=14)
_PREFIX = "runtime/oom_breadcrumb_history_v1/"
_COUNTER_KEY = _PREFIX + "sequence.json"
# A slot is [sequence,event]. Reserve room for the largest PostgreSQL bigint.
_ENVELOPE_BYTES = len("[9223372036854775807,]")


def _slot_key(index: int) -> str:
    return f"{_PREFIX}slot-{index:05d}.json"


def _encode(event: dict) -> tuple[str | None, int]:
    try:
        raw = json.dumps(event, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        return raw, len(raw.encode("utf-8")) + _ENVELOPE_BYTES
    except (TypeError, ValueError):
        return None, 0


class HistoryBudget:
    """Reserve bytes for one report run or for a process outside a report.

    Failed slot writes consume their reservation. The omission count records
    events or details dropped during preparation, before any storage attempt.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self._lock = Lock()
        self._used = 0
        self._omitted = 0

    def reserve(self, payload: dict) -> tuple[str | None, int]:
        with self._lock:
            remaining = min(_SLOT_BYTES, _BUDGET_BYTES - self._used)
            event = {**payload, "history_omitted": self._omitted}
            raw, size = _encode(event)
            if raw is None or size > remaining:
                self._omitted += 1
                if "detail" not in event:
                    return None, self._omitted
                del event["detail"]
                event["history_omitted"] = self._omitted
                raw, size = _encode(event)
                if raw is None or size > remaining:
                    return None, self._omitted
            self._used += size
            return raw, self._omitted


process_budget = HistoryBudget()
_report_budget: ContextVar[HistoryBudget | None] = ContextVar("oom_report_budget", default=None)


@contextmanager
def report_budget_scope():
    token = _report_budget.set(HistoryBudget())
    try:
        yield
    finally:
        _report_budget.reset(token)


def reserve_history(payload: dict) -> tuple[str | None, int]:
    return (_report_budget.get() or process_budget).reserve(payload)


def _reset_after_fork() -> None:
    process_budget.reset()
    _report_budget.set(None)


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_after_fork)


def append_history(storage, raw: str, at: str) -> None:
    if storage.using_postgres():
        storage.init_db()
        with closing(storage._conn()) as conn, conn, conn.cursor() as cur:
            # The counter's row lock serializes allocation and the matching
            # upsert. A rollback leaves both the slot and the counter unchanged.
            cur.execute(
                """INSERT INTO app_kv_store (name, payload, updated_at)
                   VALUES (%s, '1', %s) ON CONFLICT (name) DO UPDATE
                   SET payload = (app_kv_store.payload::bigint + 1)::text,
                       updated_at = EXCLUDED.updated_at
                   RETURNING payload""",
                (_COUNTER_KEY, at),
            )
            sequence = int(cur.fetchone()[0])
            cur.execute(
                """INSERT INTO app_kv_store (name, payload, updated_at)
                   VALUES (%s, %s, %s) ON CONFLICT (name) DO UPDATE
                   SET payload = EXCLUDED.payload, updated_at = EXCLUDED.updated_at""",
                (_slot_key((sequence - 1) % _SLOT_COUNT), f"[{sequence},{raw}]", at),
            )
        return

    storage._require_local_allowed("append_breadcrumb_history")
    import fcntl

    counter = storage.base_dir / _COUNTER_KEY
    counter.parent.mkdir(parents=True, exist_ok=True)
    with counter.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        sequence = int(counter.read_text(encoding="utf-8")) + 1 if counter.exists() else 1
        # Each file replacement is atomic. An interrupted reservation can leave
        # a gap, and the next writer advances to the following slot.
        storage._atomic_write_text(counter, str(sequence))
        slot = storage.base_dir / _slot_key((sequence - 1) % _SLOT_COUNT)
        storage._atomic_write_text(slot, f"[{sequence},{raw}]")


def read_history(storage, limit: int) -> list[dict]:
    limit = min(limit, _SLOT_COUNT)
    if limit <= 0:
        return []
    now = datetime.now(timezone.utc)
    floor = (now - _RETENTION).isoformat(timespec="milliseconds")
    ceiling = now.isoformat(timespec="milliseconds")
    if storage.using_postgres():
        storage.init_db()
        with closing(storage._conn()) as conn:
            conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM app_kv_store WHERE name=%s", (_COUNTER_KEY,))
                counter = cur.fetchone()
                if not counter:
                    return []
                sequence = int(counter[0])
                newest = (sequence - 1) % _SLOT_COUNT
                ranges = [(0, newest)]
                if sequence > _SLOT_COUNT and newest < _SLOT_COUNT - 1:
                    ranges.append((newest + 1, _SLOT_COUNT - 1))
                entries = []
                # Within a ring leg, slot order is also persistence order.
                # Read the head and both legs from the same snapshot.
                for first, last in ranges:
                    cur.execute(
                        """SELECT payload FROM app_kv_store
                           WHERE name BETWEEN %s AND %s AND updated_at BETWEEN %s AND %s
                           ORDER BY name DESC LIMIT %s""",
                        (_slot_key(first), _slot_key(last), floor, ceiling, limit - len(entries)),
                    )
                    entries.extend(json.loads(row[0])[1] for row in cur.fetchall())
                    if len(entries) == limit:
                        break
                return entries[::-1]

    storage._require_local_allowed("read_breadcrumb_history")
    slots = (storage.base_dir / _PREFIX).glob("slot-[0-9][0-9][0-9][0-9][0-9].json")
    entries = (json.loads(path.read_text(encoding="utf-8")) for path in slots)
    in_window = (item for item in entries if floor <= item[1]["at"] <= ceiling)
    recent = nlargest(limit, in_window, key=lambda item: item[0])
    return [event for _, event in reversed(recent)]
