"""Durable seal for approved Autonomy production parameters."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from app_version import APP_VERSION
from persistent_config_store import read_persistent_json, write_persistent_json

KEY = "controlled_learning/parameter_integrity.json"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _snapshot() -> dict[str, Any]:
    from autonomous_portfolio import load_parameters
    from controlled_parameter_learning import ensure_champion_version
    champion = ensure_champion_version()
    parameters = dict(load_parameters().normalized().__dict__)
    payload = {"parameters": parameters, "champion_version_id": champion.get("version_id")}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    return {**payload, "fingerprint": digest}


def write_approved_seal(*, approval_id: str, reason: str) -> dict[str, Any]:
    row = {**_snapshot(), "sealed_at": _now(), "approval_id": approval_id, "reason": reason,
           "app_version": APP_VERSION, "status": "APPROVED"}
    write_persistent_json(KEY, row)
    return row


def verify_parameter_integrity(*, notify: bool = False) -> dict[str, Any]:
    current = _snapshot()
    sealed = read_persistent_json(KEY, default=None)
    if not isinstance(sealed, Mapping):
        return write_approved_seal(approval_id="BOOTSTRAP", reason="Første integritetsforsegling")
    if str(sealed.get("fingerprint")) == current["fingerprint"]:
        return {**current, "status": "APPROVED", "sealed_at": sealed.get("sealed_at"),
                "approval_id": sealed.get("approval_id")}
    result = {**current, "status": "BLOCKED_UNAPPROVED", "expected_fingerprint": sealed.get("fingerprint"),
              "detected_at": _now(), "reason": "Produksjonsparametere avviker fra siste godkjente forsegling"}
    from autonomous_portfolio import set_status
    set_status(False, result["reason"])
    previous = read_persistent_json(KEY + ".alert", default={})
    if notify and (not isinstance(previous, Mapping) or previous.get("fingerprint") != current["fingerprint"]):
        try:
            from notifier import send_pushover_alert
            send_pushover_alert(result["reason"] + ". Autonomi er pauset.", title="⛔ Autonomi parameteravvik")
        finally:
            write_persistent_json(KEY + ".alert", {"fingerprint": current["fingerprint"], "at": _now()})
    return result
