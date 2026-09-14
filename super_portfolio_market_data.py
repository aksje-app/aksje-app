"""Bounded price-history acquisition for Super Portfolio coarse discovery."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import os
import time
from typing import Any, Callable, Mapping, Sequence


DEFAULT_BATCH_SIZE = 40
DEFAULT_MAX_WORKERS = 2
DEFAULT_REQUEST_TIMEOUT = 20
MAX_CONSECUTIVE_FAILED_BATCHES = 3


class ScanCancelled(RuntimeError):
    pass


class ResourceLimitReached(RuntimeError):
    pass


def _memory_allows_next_batch() -> bool:
    try:
        from runtime_memory import memory_snapshot
        snapshot = dict(memory_snapshot() or {})
        limit = float(snapshot.get("cgroup_memory_limit_mb") or 0)
        current = float(snapshot.get("cgroup_memory_current_mb") or snapshot.get("process_rss_mb") or 0)
        reserve = max(96.0, float(os.getenv("SP_MEMORY_RESERVE_MB", "128") or 128))
        return not limit or current + reserve < limit
    except Exception:
        return True


def _close_rows(frame: Any, symbol: str, single: bool) -> list[dict[str, Any]]:
    try:
        if single:
            close = frame["Close"]
        elif symbol in frame.columns.get_level_values(0):
            close = frame[symbol]["Close"]
        else:
            close = frame["Close"][symbol]
        if hasattr(close, "columns"):
            close = close.iloc[:, 0]
        return [
            {"date": index.date().isoformat() if hasattr(index, "date") else str(index)[:10], "close": float(value)}
            for index, value in close.dropna().items()
        ]
    except Exception:
        return []


def _download_batch(batch: Sequence[str], start_date: str, timeout: int) -> dict[str, list[dict[str, Any]]]:
    import yfinance as yf
    symbols = list(batch)
    end = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
    frame = yf.download(
        symbols, start=start_date, end=end, interval="1d", progress=False,
        auto_adjust=True, threads=False, group_by="ticker", timeout=int(timeout),
    )
    if frame is None or getattr(frame, "empty", True):
        return {symbol: [] for symbol in symbols}
    single = len(symbols) == 1
    return {symbol: _close_rows(frame, symbol, single) for symbol in symbols}


def _download_with_retry(batch: Sequence[str], start_date: str, timeout: int) -> tuple[dict[str, list[dict[str, Any]]], str]:
    last_error = ""
    for attempt in range(2):
        try:
            return _download_batch(batch, start_date, timeout), ""
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"[:500]
            if attempt == 0:
                time.sleep(0.5)
    return {}, last_error


def load_price_series_bounded(
    symbols: Sequence[str],
    start_date: str,
    *,
    progress_callback: Callable[[Mapping[str, Any]], None] | None,
    control_callback: Callable[[], str] | None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_workers: int = DEFAULT_MAX_WORKERS,
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    clean = sorted({str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()})
    size = max(1, min(50, int(batch_size)))
    workers = max(1, min(2, int(max_workers)))
    batches = [clean[offset:offset + size] for offset in range(0, len(clean), size)]
    output: dict[str, list[dict[str, Any]]] = {}
    failed_batches = 0
    consecutive_failures = 0
    completed = 0
    circuit_open = False

    def check_control() -> None:
        action = str(control_callback() if control_callback else "RUN").upper()
        if action == "STOP":
            raise ScanCancelled("SP scan cancelled")
        while action == "PAUSE":
            time.sleep(5)
            action = str(control_callback() if control_callback else "RUN").upper()
            if action == "STOP":
                raise ScanCancelled("SP scan cancelled")

    for window_start in range(0, len(batches), workers):
        window = batches[window_start:window_start + workers]
        check_control()
        if not _memory_allows_next_batch():
            raise ResourceLimitReached("SP memory reserve would be crossed")
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="sp-price") as executor:
            futures = {}
            for relative, batch in enumerate(window):
                check_control()
                batch_number = window_start + relative + 1
                futures[executor.submit(_download_with_retry, batch, start_date, request_timeout)] = (batch_number, batch)
            for future in as_completed(futures):
                batch_number, batch = futures[future]
                rows, error = future.result()
                if error:
                    failed_batches += 1
                    consecutive_failures += 1
                else:
                    output.update(rows)
                    consecutive_failures = 0
                completed += len(batch)
                if progress_callback:
                    progress_callback({
                        "phase": "COARSE_PRICE", "completed": min(completed, len(clean)), "total": len(clean),
                        "batch": batch_number, "batches": len(batches), "ticker": batch[-1] if batch else "",
                        "message": f"Grovskann {min(completed, len(clean))}/{len(clean)}",
                        "error": error,
                    })
                try:
                    from runtime_memory import release_process_memory
                    release_process_memory("sp:coarse_batch")
                except Exception:
                    pass
                if consecutive_failures >= MAX_CONSECUTIVE_FAILED_BATCHES:
                    circuit_open = True
                    break
        if circuit_open:
            break

    health = {
        "requested_symbols": len(clean), "completed_symbols": min(completed, len(clean)),
        "returned_symbols": len(output), "failed_batches": failed_batches,
        "total_batches": len(batches), "circuit_open": circuit_open,
    }
    return output, health
