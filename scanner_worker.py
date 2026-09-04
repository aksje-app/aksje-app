import logging
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
from cron_control import should_run_background_scan, mark_background_scan_started
from currency_alert_service import run_currency_alert_checks

AUTOMATED_SCANNER_MARKETS = ("USA", "NORGE", "SVERIGE")


def _open_automated_markets():
    try:
        values = open_markets(AUTOMATED_SCANNER_MARKETS)
    except TypeError:  # compatibility with older injected/test providers
        values = open_markets()
    return [market for market in values if market in AUTOMATED_SCANNER_MARKETS]


def _automated_market_status_lines():
    try:
        return market_status_lines(AUTOMATED_SCANNER_MARKETS)
    except TypeError:  # compatibility with older injected/test providers
        return market_status_lines()

def _filter_items_by_settings(items, settings):
    allowed = set(enabled_markets(settings))
    max_per = int(settings.get("max_tickers_per_market", 20))
    counts = {"USA": 0, "NORGE": 0, "SVERIGE": 0}
    out = []
    for item in items:
        ticker = item.get("ticker", item if isinstance(item, str) else "")
        market = _ticker_market(ticker)
        if market not in allowed:
            continue
        if counts[market] >= max_per:
            continue
        counts[market] += 1
        out.append(item)
    return out

from settings_store import load_settings, enabled_markets

import os
import time
import requests
import hashlib
import re
from datetime import datetime, timezone
from paper_scanner_runtime import (
    clear_scanner_checkpoint, load_scanner_checkpoint, load_scanner_status,
    run_coordinated, save_scanner_checkpoint, scanner_configuration_snapshot,
    update_scanner_status,
)

from paper_store import force_schema_migration
from paper_trading import auto_trade, paper_buy, load_portfolio, portfolio_value
from alert_state import should_send_alert, record_alert
from market_hours import open_markets, should_process_ticker, market_status_lines, ticker_market as _ticker_market
from background_guard import print_market_guard_summary

from stocks import get_sp500_tickers, get_norwegian_tickers, get_swedish_tickers, US_FALLBACK, NORWEGIAN_STOCKS, SWEDISH_STOCKS
from analysis import release_score_caches, score_stock
from runtime_memory import memory_snapshot, release_process_memory
from technical import calculate_rsi, calculate_macd, detect_trend
from patterns import breakout_scanner, detect_head_shoulders, detect_inverse_head_shoulders
from signal_engine import build_trading_decision
from services.market_snapshot_service import get_market_snapshot_service
from services.parallel_strategy_service import get_parallel_strategy_service
from services.production_strategy_service import get_production_strategy_service
from services.strategy_account_service import get_strategy_account_service
from services.simulated_execution_service import get_simulated_execution_service
from services.paper_quality_enrichment_service import get_paper_quality_enrichment_service
from runtime_safety import paper_trading_decision
from ticker_health import quarantine_status, record_ticker_failure, record_ticker_success


def _paper_candidate_context(result):
    """Build the minimum auditable order-gate context from one scanner result."""
    result = result or {}
    candidate = dict(result.get("candidate_snapshot") or {})
    decision = dict(result.get("decision") or {})
    candidate["portfolio_action"] = str(decision.get("decision") or result.get("signal") or "").upper()
    candidate["valid_for_decision"] = bool(result.get("price") is not None and result.get("candidate_snapshot"))
    candidate["evidence_valid_for_decision"] = bool(result.get("candidate_snapshot"))
    candidate["decision_source"] = "technical_production_strategy"
    return candidate


force_schema_migration()

SCANNER_MAX_TICKERS = int(os.getenv("SCANNER_MAX_TICKERS", "30"))
SCAN_SLEEP_SECONDS = float(os.getenv("SCAN_SLEEP_SECONDS", "0.2"))
from notifier import normalize_notification_result, send_pushover_alert  # canonical notifier


_SCANNER_TICKER_RE = re.compile(r"^[A-Z0-9.^=\-]{1,24}$")


def valid_scanner_ticker(value) -> bool:
    """Accept Yahoo-style symbols, never fund names or arbitrary UI labels."""
    return bool(_SCANNER_TICKER_RE.fullmatch(str(value or "").strip().upper()))


def _clean_scanner_tickers(values):
    clean = []
    seen = set()
    for value in values or []:
        ticker = str(value or "").strip().upper()
        if not valid_scanner_ticker(ticker):
            if ticker:
                print(f"Ugyldig scanner-ticker filtrert bort: {ticker[:80]}")
            continue
        if ticker not in seen:
            seen.add(ticker)
            clean.append(ticker)
    return clean


def _take(fn, n):
    try:
        return fn(n)
    except TypeError:
        return fn()[:n]




def _merge_unique(*lists):
    out = []
    seen = set()
    for lst in lists:
        for t in lst or []:
            t = str(t).upper()
            if valid_scanner_ticker(t) and t not in seen:
                seen.add(t)
                out.append(t)
    return out


def build_cron_technical_context(item):
    """Compatibility wrapper around the canonical v19.6.0 snapshot builder."""
    try:
        return get_market_snapshot_service().technical_context_from_history((item or {}).get("hist"))
    except Exception as exc:
        print(f"Teknisk context feilet: {exc}")
        return {}


def latest_ui_buy_candidate_tickers(settings=None):
    """
    Kjøp nå-listen i UI lagres i settings_store.
    Cron prioriterer disse først, slik at UI og Cron vurderer samme aksjer.
    """
    settings = settings or load_settings()
    out = []
    seen = set()

    for row in settings.get("latest_buy_now_candidates", []) or []:
        ticker = str(row.get("ticker", "")).upper()
        if valid_scanner_ticker(ticker) and ticker not in seen:
            seen.add(ticker)
            out.append(ticker)

    return out

def get_watchlist():
    settings = load_settings()
    enabled = set(enabled_markets(settings)) & set(AUTOMATED_SCANNER_MARKETS)
    markets = _open_automated_markets()
    custom = os.getenv("SCANNER_WATCHLIST", "").strip()
    if custom:
        return [ticker for ticker in _clean_scanner_tickers(custom.replace(";", ",").split(","))
                if _ticker_market(ticker) in enabled][:max(1, SCANNER_MAX_TICKERS)]

    max_per_market = int(settings.get("max_tickers_per_market", 20))
    scan_top_only = bool(settings.get("scan_top_picks_only", True))
    tickers = []

    # 1) Kandidater som UI nettopp viste som KJØP NÅ prioriteres først.
    ui_candidates = latest_ui_buy_candidate_tickers(settings)
    open_ui_candidates = [ticker for ticker in ui_candidates if _ticker_market(ticker) in markets]
    if open_ui_candidates:
        print(f"Prioriterer åpne UI Kjøp nå-kandidater: {open_ui_candidates}")
        tickers += open_ui_candidates

    # 2) Deretter kjente store/top-picks-kandidater.
    # Før var S&P-listen ofte alfabetisk, og AVGO/NVDA/AMZN kunne komme for sent.
    if "USA" in markets and "USA" in enabled:
        sp = _take(get_sp500_tickers, max(SCANNER_MAX_TICKERS, max_per_market))
        if scan_top_only:
            tickers += _merge_unique(US_FALLBACK, sp)[:max_per_market]
        else:
            tickers += _merge_unique(US_FALLBACK, sp)[:max(SCANNER_MAX_TICKERS, max_per_market)]

    if "NORGE" in markets and "NORGE" in enabled:
        no = _take(get_norwegian_tickers, max_per_market)
        tickers += _merge_unique(NORWEGIAN_STOCKS, no)[:max_per_market]

    if "SVERIGE" in markets and "SVERIGE" in enabled:
        se = _take(get_swedish_tickers, max_per_market)
        tickers += _merge_unique(SWEDISH_STOCKS, se)[:max_per_market]

    out = []
    seen = set()
    for t in _clean_scanner_tickers(tickers):
        if t not in seen:
            seen.add(t)
            out.append(t)

    # Åpne posisjoner må prioriteres for stop-loss/take-profit/trailing, men
    # SCANNER_MAX_TICKERS er en hard kontrakt for én skannesyklus.  Tidligere
    # kunne max_per_market og et gjenopptatt kontrollpunkt utvide en 30-grense
    # til 50 eller mer, slik produksjonsdiagnosen 04.09.2026 dokumenterte.
    current_positions = list(load_portfolio().get("positions", {}).keys())
    prioritized_positions = []
    for t in current_positions:
        t = str(t).upper()
        if valid_scanner_ticker(t) and _ticker_market(t) in enabled and t not in prioritized_positions:
            prioritized_positions.append(t)
    return _merge_unique(prioritized_positions, out)[:max(1, SCANNER_MAX_TICKERS)]


def scanner_memory_decision(memory, *, soft_limit_mb, minimum_headroom_mb=80.0):
    """Return an auditable decision instead of an unexplained boolean gate."""
    snapshot = dict(memory or {})
    current = snapshot.get("cgroup_memory_current_mb")
    rss = snapshot.get("process_rss_mb")
    used_mb = float(current if current is not None else (rss or 0))
    raw_headroom = snapshot.get("cgroup_memory_headroom_mb")
    headroom_mb = float(raw_headroom) if raw_headroom is not None else None
    reasons = []
    if used_mb >= float(soft_limit_mb):
        reasons.append("SOFT_LIMIT")
    if headroom_mb is not None and headroom_mb < float(minimum_headroom_mb):
        reasons.append("CGROUP_HEADROOM")
    return {
        "pressure": bool(reasons),
        "reasons": reasons,
        "reason": "+".join(reasons) if reasons else "NONE",
        "configured_soft_limit_mb": float(soft_limit_mb),
        "minimum_headroom_mb": float(minimum_headroom_mb),
        "used_mb": used_mb,
        "cgroup_limit_mb": snapshot.get("cgroup_memory_limit_mb"),
        "cgroup_headroom_mb": headroom_mb,
        "process_rss_mb": snapshot.get("process_rss_mb"),
    }


def _memory_policy_line(decision):
    limit = decision.get("cgroup_limit_mb")
    headroom = decision.get("cgroup_headroom_mb")
    line = (
        f"Scanner minnevern: brukt={decision['used_mb']:.1f} MB, "
        f"softgrense={decision['configured_soft_limit_mb']:.1f} MB, "
        + (f"cgroup-grense={float(limit):.1f} MB" if limit is not None else "cgroup-grense=ukjent")
    )
    return line + (f", ledig={float(headroom):.1f} MB" if headroom is not None else ", ledig=ukjent")



def get_latest_price(item):
    price = item.get("price")
    if price:
        return float(price)

    hist = item.get("hist")
    if hist is not None and "Close" in hist:
        close = hist["Close"].dropna()
        if len(close) > 0:
            return float(close.iloc[-1])

    return None


def get_rsi_values(item):
    try:
        hist = item.get("hist")
        if hist is not None and "RSI" in hist:
            rsi = hist["RSI"].dropna()
            if len(rsi) >= 2:
                return float(rsi.iloc[-1]), float(rsi.iloc[-2])
            if len(rsi) == 1:
                return float(rsi.iloc[-1]), None
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)

    return None, None


def analyze_ticker(ticker, *, market_snapshot_id="", run_id=""):
    quarantine = quarantine_status(ticker)
    if quarantine.get("active"):
        print(f"⏸ {ticker}: midlertidig datakarantene til {quarantine.get('quarantined_until')} etter gjentatte tomme svar")
        return None
    try:
        item = score_stock(ticker, use_news=False)
    except Exception as exc:
        logging.warning("Markedsdatafeil isolert for %s: %s: %s", ticker, type(exc).__name__, str(exc)[:180])
        record_ticker_failure(ticker, f"{type(exc).__name__}: {str(exc)[:180]}")
        return None
    if not item:
        record_ticker_failure(ticker, "NO_MARKET_DATA: score_stock returned empty")
        return None

    price = get_latest_price(item)
    if price is None:
        print(f"{ticker}: mangler pris")
        record_ticker_failure(ticker, "NO_MARKET_PRICE")
        return None
    record_ticker_success(ticker)

    snapshot_service = get_market_snapshot_service()
    technical_context = build_cron_technical_context(item)
    # Enrich only the immutable snapshot evidence. The legacy technical score
    # and trading decision remain authoritative and unchanged.
    try:
        item = get_paper_quality_enrichment_service().enrich(item, technical_context)
    except Exception as exc:
        logging.warning("Paper quality enrichment failed open for %s: %s", ticker, exc)
    candidate_snapshot = snapshot_service.build_candidate_snapshot(
        item, technical_context, market_snapshot_id=market_snapshot_id, run_id=run_id, source="paper_scanner"
    )
    base_decision = build_trading_decision(candidate_snapshot.to_dict(), technical_context)
    decision = get_production_strategy_service().evaluate_technical(
        candidate_snapshot, base_decision, run_id=run_id or market_snapshot_id or ticker, portfolio_state=load_portfolio(),
    )

    signal = decision.get("decision", "HOLD / WAIT")
    confidence = int(decision.get("confidence", 0) or 0)
    score = float(decision.get("decision_score", decision.get("final_score", item.get("score", 0))) or 0)
    rsi, prev_rsi = get_rsi_values(item)

    # Fallback: bruk RSI fra context dersom hist ikke har egen RSI-kolonne.
    if rsi is None:
        rsi = technical_context.get("rsi")

    return {
        "ticker": ticker,
        "price": price,
        "item": item,
        "decision": decision,
        "signal": signal,
        "confidence": confidence,
        "score": score,
        "rsi": rsi,
        "prev_rsi": prev_rsi,
        "technical_context": technical_context,
        "candidate_snapshot": candidate_snapshot.to_dict(),
        "market_snapshot_id": candidate_snapshot.market_snapshot_id,
        "candidate_snapshot_id": candidate_snapshot.candidate_snapshot_id,
    }


def maybe_send_trade_alert(result, msg):
    ticker = result["ticker"]
    signal = result["signal"]

    ok_alert, reason = should_send_alert(ticker, signal)
    if not ok_alert:
        print(f"🔕 {ticker}: trade-varsel blokkert ({reason})")
        return False

    sent, _detail = normalize_notification_result(send_pushover_alert(
        f"🧪 {msg}\nPris: {result['price']:.2f}\nConfidence: {result['confidence']}%",
        title="Auto Paper Trading",
    ))

    if sent:
        record_alert(
            ticker,
            signal,
            {"price": result["price"], "confidence": result["confidence"], "trade_msg": msg},
        )

    return sent


def _run_once_impl(force=False, *, check_currency_alerts=True):
    effective_scanner_configuration = scanner_configuration_snapshot()
    # Currency alerts are independent of the stock scanner gate and market hours.
    # This must run before should_run_background_scan(), otherwise closed markets,
    # pause windows or scanner cooldowns silently suppress every FX alert.
    if check_currency_alerts:
        try:
            fx_results = run_currency_alert_checks(force=force, source="scanner_worker")
            for fx in fx_results:
                print(
                    f"FX {fx.get('pair')}: {fx.get('status')} "
                    f"rate={fx.get('rate', '-')} sent={fx.get('sent', False)} "
                    f"reason={fx.get('reason', '-')}"
                )
        except Exception as exc:
            print(f"Valutavarsel-kontroll feilet: {exc}")

    if force:
        print("Cron control: FORCE=true, kjører auto-motor nå")
    else:
        _allowed, _reason = should_run_background_scan()
        print(f"Cron control: {_reason}")
        if not _allowed:
            print("⏸ Cron våknet, aksjescanner kjører ikke nå. Valutavarsler er allerede kontrollert.")
            update_scanner_status(state="SKIPPED_POLICY", message=_reason)
            return 0
        mark_background_scan_started()

    print_market_guard_summary()
    for line in _automated_market_status_lines():
        print(line)

    markets = _open_automated_markets()
    if not markets:
        print("⏸ Alle markeder stengt - ingen scanning")
        update_scanner_status(state="MARKET_CLOSED", markets_open=[], message="Alle markeder er stengt")
        return 0

    print(f"Åpne markeder: {markets}")
    settings = load_settings()
    auto_trading_enabled = bool(settings.get("auto_trading_enabled", False))
    if bool(settings.get("auto_trading_paused", False)):
        auto_trading_enabled = False
        print("⏸ Auto trading er pauset i app-innstillinger")
    if bool(settings.get("auto_trading_emergency_stop", False)):
        auto_trading_enabled = False
        print("🧯 Auto trading er i NØDSTOPP - ingen nye handler")
    min_buy_score = float(settings.get("min_buy_score", 7.2))
    min_buy_confidence = int(settings.get("min_buy_confidence", 70))
    if not auto_trading_enabled:
        print("⏸ Auto trading er deaktivert i app-innstillinger")

    checkpoint = load_scanner_checkpoint()
    current_tickers = get_watchlist()
    checkpoint_tickers = _clean_scanner_tickers(checkpoint.get("tickers") or [])
    hard_limit = max(1, int(effective_scanner_configuration["scanner_max_tickers"]))
    if checkpoint.get("scan_run_id") and checkpoint_tickers:
        # Finish exactly the original bounded universe. New symbols belong to
        # the next scan; appending them here previously made a 30-symbol run
        # grow to 50 while it was being resumed.
        tickers = checkpoint_tickers[:hard_limit]
        resume = True
    else:
        tickers = current_tickers[:hard_limit]
        current_signature = hashlib.sha256("\n".join(tickers).encode("utf-8")).hexdigest()
        resume = bool(checkpoint.get("ticker_signature") == current_signature and checkpoint.get("scan_run_id"))
    tickers = _clean_scanner_tickers(tickers)[:hard_limit]
    print(f"Scanner {len(tickers)}/{hard_limit} tickers: {tickers}")

    snapshot_service = get_market_snapshot_service()
    ticker_signature = hashlib.sha256("\n".join(tickers).encode("utf-8")).hexdigest()
    scan_run_id = str(checkpoint.get("scan_run_id")) if resume else f"PAPER-SCAN-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    update_scanner_status(scan_run_id=scan_run_id, markets_open=markets, tickers_total=len(tickers), tickers_processed=0)
    market_snapshot_id = snapshot_service.new_snapshot_id(run_id=scan_run_id, source="paper_scanner")
    allowed_ticker_set = {str(t).upper() for t in tickers}
    candidate_snapshots = [
        row for row in list(checkpoint.get("candidate_snapshots") or [])
        if str((row or {}).get("ticker") or "").upper() in allowed_ticker_set
    ] if resume else []
    latest_prices = {
        str(key).upper(): value for key, value in dict(checkpoint.get("latest_prices") or {}).items()
        if str(key).upper() in allowed_ticker_set
    } if resume else {}
    trades_executed = int(checkpoint.get("trades_executed") or 0) if resume else 0
    start_index = max(0, min(len(tickers), int(checkpoint.get("next_index") or 0))) if resume else 0
    if resume:
        print(f"Gjenopptar komplett skanning ved ticker {start_index + 1}/{len(tickers)}; ingen tickere fjernes")

    memory_policy_logged = False
    for ticker_index, ticker in enumerate(tickers[start_index:], start=start_index + 1):
        cleanup_before_gate = release_process_memory("paper_scanner:pre_ticker_gate")
        memory = cleanup_before_gate.get("after") or memory_snapshot()
        soft_limit_mb = float(effective_scanner_configuration["scanner_memory_soft_limit_mb"])
        minimum_progress = int(effective_scanner_configuration["scanner_min_tickers_per_cycle"])
        processed_this_cycle = (ticker_index - 1) - start_index
        used_mb = float(memory.get("cgroup_memory_current_mb") or memory.get("process_rss_mb") or 0)
        memory_decision = scanner_memory_decision(memory, soft_limit_mb=soft_limit_mb)
        memory_pressure = bool(memory_decision["pressure"])
        if not memory_policy_logged:
            print(_memory_policy_line(memory_decision))
            update_scanner_status(memory=memory, memory_policy=memory_decision)
            memory_policy_logged = True
        if memory_pressure and processed_this_cycle >= minimum_progress:
            save_scanner_checkpoint({
                "ticker_signature": ticker_signature, "scan_run_id": scan_run_id,
                "tickers": tickers,
                "next_index": ticker_index - 1, "candidate_snapshots": candidate_snapshots,
                "latest_prices": latest_prices, "trades_executed": trades_executed,
            })
            update_scanner_status(
                state="PARTIAL_CHECKPOINT", scan_run_id=scan_run_id,
                tickers_processed=ticker_index - 1, tickers_total=len(tickers),
                trades_executed=trades_executed, memory=memory,
                memory_policy=memory_decision, memory_pressure_reason=memory_decision["reason"],
                message="Minnemykt kontrollpunkt lagret; neste cron fortsetter automatisk med resterende tickere",
            )
            print(
                f"Minnemykt kontrollpunkt ved {used_mb:.1f} MB; årsak={memory_decision['reason']} etter "
                f"{processed_this_cycle} ticker(e) denne cron; neste indeks {ticker_index}/{len(tickers)}"
            )
            return trades_executed
        if memory_pressure:
            print(
                f"Minnepress ved {used_mb:.1f} MB; årsak={memory_decision['reason']}, men gjennomfører minst "
                f"{minimum_progress} ticker(e) for å sikre fremdrift"
            )
        result = None
        try:
            update_scanner_status(
                scan_run_id=scan_run_id, current_ticker=str(ticker),
                tickers_processed=ticker_index - 1, trades_executed=trades_executed,
            )
            if not should_process_ticker(ticker):
                print(f"⏸ {ticker}: marked stengt")
                continue

            result = analyze_ticker(ticker, market_snapshot_id=market_snapshot_id, run_id=scan_run_id)
            if result is None:
                continue

            latest_prices[ticker] = result["price"]
            if isinstance(result.get("candidate_snapshot"), dict):
                candidate_snapshots.append(result["candidate_snapshot"])

            print(
                f"{ticker}: {result['signal']} "
                f"conf={result['confidence']} "
                f"score={result['score']:.2f} "
                f"price={result['price']:.2f}"
            )

            paper_gate = paper_trading_decision()
            if paper_gate.allowed and auto_trading_enabled:
                signal_text = str(result["signal"]).upper()
                allow_trade = True
                open_positions = (load_portfolio() or {}).get("positions", {}) or {}
                has_existing_position = str(result["ticker"]).upper() in {str(t).upper() for t in open_positions.keys()}

                if has_existing_position:
                    traded, msg = auto_trade(
                        result["ticker"],
                        result["price"],
                        result["signal"],
                        confidence=result["confidence"],
                        rsi=result.get("rsi"),
                        prev_rsi=result.get("prev_rsi"),
                        trade_context={"source": "scanner_worker", "automatic": True, "run_id": scan_run_id, "scan_id": scan_run_id, "scanner_execution_id": load_scanner_status().get("execution_id"), "market_data_at": result.get("market_data_at") or result.get("as_of") or "", "candidate": _paper_candidate_context(result)},
                    )
                    print(f"Auto risk check {ticker}: {msg}")

                    if traded:
                        trades_executed += 1
                        print("Trade-varsling håndteres av trading_engine")
                    continue

                if "BUY" in signal_text:
                    if result["score"] < min_buy_score:
                        print(f"⏸ {ticker}: BUY blokkert - score {result['score']:.2f} < min {min_buy_score}")
                        allow_trade = False
                    elif result["confidence"] < min_buy_confidence:
                        print(f"⏸ {ticker}: BUY blokkert - confidence {result['confidence']} < min {min_buy_confidence}")
                        allow_trade = False

                    if allow_trade:
                        print(f"✅ {ticker}: BUY-kandidat godkjent, prøver paper_buy direkte")
                        traded, msg = paper_buy(
                            result["ticker"],
                            result["price"],
                            result["confidence"],
                            "AUTO BUY via Cron/Kjøp nå",
                            trade_context={
                                "source": "scanner_worker",
                                "automatic": True,
                                "run_id": scan_run_id,
                                "scan_id": scan_run_id,
                                "scanner_execution_id": load_scanner_status().get("execution_id"),
                                "market_data_at": result.get("market_data_at") or result.get("as_of") or "",
                                "candidate": _paper_candidate_context(result),
                            },
                        )
                        print(f"Auto BUY {ticker}: {msg}")

                        if traded:
                            trades_executed += 1
                            print("Trade-varsling håndteres av trading_engine")
                    else:
                        print(f"Auto BUY {ticker}: blokkert av regler")

                else:
                    traded, msg = auto_trade(
                        result["ticker"],
                        result["price"],
                        result["signal"],
                        confidence=result["confidence"],
                        rsi=result.get("rsi"),
                        prev_rsi=result.get("prev_rsi"),
                        trade_context={"source": "scanner_worker", "automatic": True, "run_id": scan_run_id, "scan_id": scan_run_id, "scanner_execution_id": load_scanner_status().get("execution_id"), "market_data_at": result.get("market_data_at") or result.get("as_of") or "", "candidate": _paper_candidate_context(result)},
                    )
                    print(f"Auto trade {ticker}: {msg}")

                    if traded:
                        trades_executed += 1
                        print("Trade-varsling håndteres av trading_engine")

            elif not paper_gate.allowed:
                print(f"⏸ {paper_gate.reason}")

            time.sleep(SCAN_SLEEP_SECONDS)

        except Exception as e:
            print(f"Feil på {ticker}: {type(e).__name__}: {e}")
        finally:
            result = None
            release_score_caches(history=True)
            cleanup = release_process_memory(f"paper_scanner:{ticker}")
            save_scanner_checkpoint({
                "ticker_signature": ticker_signature, "scan_run_id": scan_run_id,
                "tickers": tickers,
                "next_index": ticker_index, "candidate_snapshots": candidate_snapshots,
                "latest_prices": latest_prices, "trades_executed": trades_executed,
            })
            update_scanner_status(memory=cleanup.get("after"), tickers_processed=ticker_index)

    update_scanner_status(
        scan_run_id=scan_run_id, current_ticker="", tickers_processed=len(tickers),
        trades_executed=trades_executed,
    )

    if candidate_snapshots:
        try:
            market_snapshot = snapshot_service.build_market_snapshot(
                candidate_snapshots, run_id=scan_run_id, source="paper_scanner", snapshot_id=market_snapshot_id,
                metadata={"strategy_family": "technical", "candidate_count": len(candidate_snapshots)},
            )
            save_result = snapshot_service.save(market_snapshot)
            print(f"Market snapshot {market_snapshot.snapshot_id}: saved={save_result.get('saved')} candidates={len(candidate_snapshots)}")
            try:
                parallel = get_parallel_strategy_service().evaluate_snapshot(
                    market_snapshot,
                    run_id=scan_run_id,
                    source="paper_scanner_parallel",
                    purpose="PAPER_SCANNER_PARALLEL",
                    portfolio_states={"technical": load_portfolio()},
                    families=["technical", "autonomy"],
                    context_metadata={
                        "paper_autonomy_migration_phase": "OBSERVATIONAL_INPUT",
                        "execution_authorized": False,
                    },
                )
                from paper_autonomy_bridge import publish_paper_engine_handoff
                handoff = publish_paper_engine_handoff(
                    run_id=scan_run_id,
                    market_snapshot=market_snapshot.to_dict(),
                    parallel_result=parallel,
                )
                print(
                    f"Parallel strategies {parallel.get('strategy_run_id')}: "
                    f"strategies={parallel.get('strategy_count')} decisions={parallel.get('decision_count')} "
                    f"errors={parallel.get('error_count')} paper_autonomy_inputs={handoff.get('candidate_count')}"
                )
            except Exception as parallel_exc:
                # Parallel comparison is observability only and may never stop production Paper Trading.
                print(f"Parallel strategikjøring feilet isolert: {type(parallel_exc).__name__}: {parallel_exc}")
        except Exception as exc:
            print(f"Market snapshot kunne ikke lagres: {exc}")

    portfolio = load_portfolio()
    try:
        account_service = get_strategy_account_service()
        execution_service = get_simulated_execution_service()
        technical_account = account_service.sync_legacy_account(
            "technical_benchmark_main", portfolio,
            strategy_family="technical", strategy_id="technical_benchmark",
            strategy_version_id="technical_benchmark@legacy-1.0.0",
            display_name="Teknisk benchmark", role="BENCHMARK",
            status="ACTIVE", run_id=scan_run_id,
            metadata={"source": "paper_scanner", "shared_engine_bridge": True},
        )
        mirrored = 0
        for legacy_trade in list(portfolio.get("trades") or []):
            result = execution_service.mirror_legacy_trade(
                account_id="technical_benchmark_main", trade=legacy_trade, run_id=scan_run_id
            )
            mirrored += int(bool(result.get("mirrored")))
        print(f"Shared strategy account synced: {technical_account.get('account_id')} mirrored_trades={mirrored}")
    except Exception as account_exc:
        print(f"Strategikonto-synk feilet isolert: {type(account_exc).__name__}: {account_exc}")
    value = portfolio_value(portfolio, latest_prices)
    print(f"Portfolio value: {value}")
    print(f"Cash: {portfolio.get('cash')}")
    print(f"Positions: {list(portfolio.get('positions', {}).keys())}")
    print(f"Trades executed this run: {trades_executed}")

    clear_scanner_checkpoint()
    return trades_executed


def run_once(force=False, *, check_currency_alerts=True):
    """Durable, globally coordinated unattended Paper scanner entry point."""
    def coordinated_impl(*, force=False):
        return _run_once_impl(force=force, check_currency_alerts=check_currency_alerts)

    return run_coordinated(coordinated_impl, force=force)


if __name__ == "__main__":
    run_once()
