"""Fail-closed production readiness assessment for completed report runs."""
from __future__ import annotations

from typing import Any, Mapping


ALLOWED_PRODUCTION_MARKETS = {"NORGE", "SVERIGE", "USA"}


def assess_production_readiness(run: Mapping[str, Any]) -> dict[str, Any]:
    """Separate local release quality from deploy/live production proof."""
    candidates = [row for row in (run.get("candidates") or []) if isinstance(row, Mapping)]
    scan_configuration = run.get("scan_configuration") if isinstance(run.get("scan_configuration"), Mapping) else {}
    configured = {
        str(value or "").strip().upper()
        for value in (scan_configuration.get("markets") or [])
        if str(value or "").strip()
    }
    observed = {
        str(row.get("market") or row.get("country") or "").strip().upper()
        for row in candidates
        if str(row.get("market") or row.get("country") or "").strip()
        and str(row.get("coverage_role") or "").upper() != "PORTFOLIO_ONLY_EXISTING_POSITION"
    }
    unexpected = sorted((configured | observed) - ALLOWED_PRODUCTION_MARKETS)
    moderate_trade = sorted(
        str(row.get("ticker") or "-") for row in candidates
        if str(row.get("autonomy_outcome_code") or "").upper() == "MODERAT_KJØPSANBEFALING"
        and row.get("trade_authorized") is True
    )
    local_checks = {
        "final_release_gate": bool((run.get("final_release_gate") or {}).get("ok"))
        if isinstance(run.get("final_release_gate"), Mapping) else False,
        "report_integrity": bool((run.get("report_integrity") or {}).get("ok"))
        if isinstance(run.get("report_integrity"), Mapping) else False,
        "main_pdf_valid": bool((run.get("pdf_delivery") or {}).get("validated"))
        if isinstance(run.get("pdf_delivery"), Mapping) else False,
        "technical_pdf_valid": bool((run.get("technical_pdf_delivery") or {}).get("validated"))
        if isinstance(run.get("technical_pdf_delivery"), Mapping) else False,
        "only_allowed_markets": not unexpected,
        "no_moderate_trade_authorization": not moderate_trade,
    }
    local_candidate = all(local_checks.values())
    live = run.get("live_production_verification") if isinstance(run.get("live_production_verification"), Mapping) else {}
    notification = run.get("notification") if isinstance(run.get("notification"), Mapping) else {}
    live_checks = {
        "deployed_runtime_identity": live.get("runtime_identity_match") is True,
        "scheduled_08": live.get("scheduled_08_verified") is True,
        "scheduled_14": live.get("scheduled_14_verified") is True,
        "scheduled_22": live.get("scheduled_22_verified") is True,
        "persistent_storage": live.get("persistent_storage_verified") is True,
        "pushover": live.get("pushover_verified") is True or (
            notification.get("required") is False and live.get("pushover_policy_verified") is True
        ),
        "mobile_delivery": live.get("mobile_delivery_verified") is True,
    }
    production_ready = local_candidate and all(live_checks.values())
    return {
        "status": "PRODUCTION_READY" if production_ready else (
            "LOCAL_PRODUCTION_CANDIDATE" if local_candidate else "NOT_READY"
        ),
        "production_ready": production_ready,
        "local_candidate": local_candidate,
        "local_checks": local_checks,
        "live_checks": live_checks,
        "unexpected_markets": unexpected,
        "moderate_trade_authorizations": moderate_trade,
        "note": (
            "Produksjonsklar krever bestått deploy og live kontroll av 08/14/22, "
            "lagring, Pushover og mobil fildeling. Lokal validering alene er ikke nok."
        ),
    }
