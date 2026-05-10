"""Single source of truth for the deployed app version."""

from __future__ import annotations

APP_VERSION = "v18.5.22"
APP_VERSION_NAME = "Strict Universe Mode + Progress UI"
APP_BUILD_LABEL = f"{APP_VERSION} {APP_VERSION_NAME}"


def get_app_version() -> str:
    """Return the current app version used by UI and service metadata."""
    return APP_VERSION


def get_build_label() -> str:
    """Return a human-readable build label for status panels."""
    return APP_BUILD_LABEL
