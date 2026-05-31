from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


_ENV_LOADED = False
_ENV_SOURCES: list[str] = []


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def candidate_env_paths() -> list[Path]:
    roots = [_repo_root(), Path.cwd()]
    out: list[Path] = []
    for root in roots:
        for path in (
            root / ".env",
            root / ".env" / ".env",
            root / ".env.local",
            root / "secrets.env",
        ):
            if path not in out:
                out.append(path)
    return out


def _manual_load(path: Path, *, override: bool = False) -> bool:
    loaded = False
    try:
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not key:
                continue
            if override or key not in os.environ:
                os.environ[key] = value
                loaded = True
    except Exception:
        return False
    return loaded


def load_app_env(*, override: bool = False) -> list[str]:
    global _ENV_LOADED, _ENV_SOURCES
    if _ENV_LOADED and _ENV_SOURCES and not override:
        return list(_ENV_SOURCES)

    sources: list[str] = []
    try:
        from dotenv import load_dotenv
    except Exception:
        load_dotenv = None

    for path in candidate_env_paths():
        if not path.is_file():
            continue
        loaded = False
        if load_dotenv is not None:
            try:
                loaded = bool(load_dotenv(path, override=override))
            except Exception:
                loaded = False
        if not loaded:
            loaded = _manual_load(path, override=override)
        if loaded or path not in [Path(p) for p in sources]:
            sources.append(str(path))

    _ENV_LOADED = True
    _ENV_SOURCES = sources
    return list(_ENV_SOURCES)


def env_value(name: str, default: str = "") -> str:
    load_app_env()
    return os.getenv(name, default).strip()


def has_configured_key(name: str) -> bool:
    value = env_value(name)
    return bool(value and not value.lower().startswith(("din_", "your_", "set_")))


def data_source_env_status() -> dict[str, Any]:
    sources = load_app_env()
    if not sources:
        sources = [str(path) for path in candidate_env_paths() if path.is_file()]
    finnhub_key = has_configured_key("FINNHUB_API_KEY")
    fmp_key = has_configured_key("FMP_API_KEY")
    newsapi_key = has_configured_key("NEWSAPI_KEY")
    return {
        "env_loaded": bool(sources or finnhub_key or fmp_key or newsapi_key),
        "env_sources": sources,
        "finnhub_key": finnhub_key,
        "fmp_key": fmp_key,
        "newsapi_key": newsapi_key,
        "newsapi_auto_calls": env_value("NEWSAPI_ALLOW_AUTO_CALLS", "false").lower() in {"1", "true", "yes", "on"},
    }


def redact_secrets(text: Any) -> str:
    value = str(text or "")
    if not value:
        return ""
    load_app_env()
    for key in ("FINNHUB_API_KEY", "FMP_API_KEY", "NEWSAPI_KEY"):
        secret = os.getenv(key, "").strip()
        if secret:
            value = value.replace(secret, "***")
            if len(secret) > 6:
                value = value.replace(secret[:6], "***")
    value = re.sub(r"(?i)(token|apikey|api_key|apiKey)=([^&\s]+)", r"\1=***", value)
    return value


__all__ = [
    "candidate_env_paths",
    "data_source_env_status",
    "env_value",
    "has_configured_key",
    "load_app_env",
    "redact_secrets",
]
