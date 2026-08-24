"""Durable runtime identity shared by web and unattended Render services."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from app_version import APP_VERSION
from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path

IDENTITY_INDEX_KEY = "runtime/identities.json"
IDENTITY_INDEX_PATH = runtime_data_path("runtime", "identities.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def current_runtime_identity(role: str = "") -> dict:
    commit = (os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT") or os.getenv("SOURCE_COMMIT") or "ukjent").strip()
    service = (os.getenv("RENDER_SERVICE_NAME") or os.getenv("SERVICE_NAME") or role or "lokal").strip()
    return {
        "role": str(role or service), "service": service, "version": APP_VERSION,
        "commit": commit, "commit_short": commit[:8] if commit != "ukjent" else commit,
        "branch": (os.getenv("RENDER_GIT_BRANCH") or os.getenv("GIT_BRANCH") or "ukjent").strip(),
        "observed_at": _now(),
    }


def publish_runtime_identity(role: str) -> dict:
    identity = current_runtime_identity(role)
    index = read_json(IDENTITY_INDEX_KEY, IDENTITY_INDEX_PATH, {})
    index = dict(index) if isinstance(index, dict) else {}
    index[str(role)] = identity
    write_json(IDENTITY_INDEX_KEY, IDENTITY_INDEX_PATH, index)
    return identity


def runtime_identity_snapshot() -> dict:
    index = read_json(IDENTITY_INDEX_KEY, IDENTITY_INDEX_PATH, {})
    identities = dict(index) if isinstance(index, dict) else {}
    versions = sorted({str(row.get("version")) for row in identities.values() if isinstance(row, dict) and row.get("version")})
    commits = sorted({str(row.get("commit")) for row in identities.values() if isinstance(row, dict) and row.get("commit") not in {None, "", "ukjent"}})
    return {"expected_version": APP_VERSION, "identities": identities,
            "version_mismatch": len(versions) > 1 or any(v != APP_VERSION for v in versions),
            "commit_mismatch": len(commits) > 1, "versions": versions, "commits": commits}


def validate_expected_runtime() -> tuple[bool, str]:
    expected = str(os.getenv("EXPECTED_APP_VERSION") or "").strip()
    if expected and expected != APP_VERSION:
        return False, f"Kjøretidsversjon {APP_VERSION} avviker fra EXPECTED_APP_VERSION={expected}"
    return True, "Kjøretidsversjonen samsvarer med forventet versjon." if expected else "Ingen eksplisitt forventet versjon er satt."


def validate_cluster_alignment(role: str, required_roles: tuple[str, ...] = ("web",), max_age_minutes: int = 90) -> tuple[bool, str]:
    """Require fresh peers to run the exact same release commit and version."""
    required = str(os.getenv("REQUIRE_CLUSTER_ALIGNMENT") or "").strip().lower() in {"1", "true", "yes", "on"}
    if not required:
        return True, "Automatisk klyngesamsvar er ikke aktivert i dette miljøet."
    current = current_runtime_identity(role)
    if current["commit"] == "ukjent":
        return False, "Render-commit mangler; trygg klyngesammenligning kan ikke utføres."
    snapshot = runtime_identity_snapshot()
    identities = snapshot.get("identities") or {}
    now = datetime.now(timezone.utc)
    problems: list[str] = []
    for peer_role in required_roles:
        peer = identities.get(peer_role) if isinstance(identities, dict) else None
        if not isinstance(peer, dict):
            problems.append(f"{peer_role}: identitet mangler")
            continue
        try:
            observed = datetime.fromisoformat(str(peer.get("observed_at") or "").replace("Z", "+00:00"))
            observed = observed.replace(tzinfo=observed.tzinfo or timezone.utc).astimezone(timezone.utc)
            age_minutes = (now - observed).total_seconds() / 60.0
        except Exception:
            age_minutes = max_age_minutes + 1
        if age_minutes > max_age_minutes:
            problems.append(f"{peer_role}: identitet er {age_minutes:.0f} min gammel")
        if str(peer.get("version") or "") != APP_VERSION:
            problems.append(f"{peer_role}: versjon {peer.get('version') or 'ukjent'}")
        if str(peer.get("commit") or "") != current["commit"]:
            problems.append(f"{peer_role}: commit {peer.get('commit_short') or 'ukjent'}")
    if problems:
        return False, "Distribusjon ikke synkronisert: " + "; ".join(problems)
    return True, f"{role} og {', '.join(required_roles)} kjører {APP_VERSION} / {current['commit_short']}."


def runtime_label(role: str = "") -> str:
    row = current_runtime_identity(role)
    return f"{row['version']} · commit {row['commit_short']} · {row['service']}"
