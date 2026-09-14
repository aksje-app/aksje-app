from __future__ import annotations

import os

import pytest

from repositories.application import (
    MarketSnapshotRepository,
    StrategyOrderRepository,
    StrategyFillRepository,
    StrategyAccountSnapshotRepository,
)
from services.storage_service import OversizedJsonReadError, StorageService


class FakeStorage:
    def __init__(self):
        self.values = {}
        self.reads = []
        self.slices = []

    def read_json(self, name, default=None):
        self.reads.append(name)
        return self.values.get(name, default)

    def write_json(self, name, value):
        self.values[name] = value
        return True

    def write_json_immutable(self, name, value):
        self.values.setdefault(name, value)
        return self.values[name]

    def read_json_array_slice(self, name, limit=500):
        self.slices.append((name, limit))
        value = self.values.get(name, [])
        return list(value[:limit]) if isinstance(value, list) else []

    def read_json_array_item(self, name, id_field, record_id, default=None):
        value = self.values.get(name, [])
        for row in value if isinstance(value, list) else []:
            if str(row.get(id_field) or "") == str(record_id):
                return row
        return default


def test_market_snapshot_list_never_full_reads_legacy_monolith():
    st = FakeStorage()
    st.values["repositories/market_snapshots.json"] = [
        {"snapshot_id": f"OLD-{i}", "captured_at": f"2026-08-{i+1:02d}"} for i in range(20)
    ]
    repo = MarketSnapshotRepository(st)
    rows = repo.list(limit=5)
    assert len(rows) == 5
    assert "repositories/market_snapshots.json" not in st.reads
    assert st.slices == [("repositories/market_snapshots.json", 5)]


@pytest.mark.parametrize(
    "repo_cls,legacy_key,id_field",
    [
        (StrategyOrderRepository, "repositories/strategy_orders.json", "order_id"),
        (StrategyFillRepository, "repositories/strategy_fills.json", "fill_id"),
        (StrategyAccountSnapshotRepository, "repositories/strategy_account_snapshots.json", "account_snapshot_id"),
    ],
)
def test_large_strategy_repositories_use_bounded_legacy_fallback(repo_cls, legacy_key, id_field):
    st = FakeStorage()
    st.values[legacy_key] = [{id_field: f"X-{i}"} for i in range(10)]
    rows = repo_cls(st).list(limit=3)
    assert len(rows) == 3
    assert legacy_key not in st.reads
    assert st.slices == [(legacy_key, 3)]


class FakeCursor:
    def __init__(self, payload_bytes: int):
        self.payload_bytes = payload_bytes
        self.query = ""

    def execute(self, query, params):
        self.query = str(query)

    def fetchone(self):
        if "octet_length" in self.query:
            return (self.payload_bytes,)
        raise AssertionError("Payload SELECT must never be reached for blocked monolith")


class FakeConn:
    def __init__(self, payload_bytes: int):
        self.cur = FakeCursor(payload_bytes)

    def cursor(self):
        return self.cur

    def close(self):
        pass


def test_scheduler_blocks_huge_legacy_monolith_before_payload_fetch(monkeypatch, tmp_path):
    service = StorageService(base_dir=tmp_path, database_url="postgres://example", mode="postgres", allow_local_fallback=False)
    monkeypatch.setattr(service, "using_postgres", lambda: True)
    monkeypatch.setattr(service, "init_db", lambda: None)
    monkeypatch.setattr(service, "_conn", lambda: FakeConn(135 * 1024 * 1024))
    monkeypatch.setenv("AI_RUNTIME_ROLE", "scheduler")
    monkeypatch.setenv("SCHEDULER_LARGE_JSON_WARN_MB", "20")
    with pytest.raises(OversizedJsonReadError, match="strategy_decisions"):
        service.read_json("repositories/strategy_decisions.json", [])


def test_non_scheduler_role_does_not_enable_monolith_guard(monkeypatch):
    monkeypatch.setenv("AI_RUNTIME_ROLE", "web")
    from services import storage_service as module
    assert module._scheduler_memory_safe_mode() is False
