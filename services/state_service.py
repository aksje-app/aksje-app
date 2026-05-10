"""
services/state_service.py

v18.5.11
Felles state-wrapper for Streamlit session_state.

Formål:
- redusere direkte session_state-spredning
- gi en standardisert vei for UI -> services -> state
- tåle kjøring uten Streamlit i tester
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


class StateService:
    def __init__(self, session_state: Optional[Any] = None):
        self.session_state = session_state

    def _state(self) -> Any:
        if self.session_state is not None:
            return self.session_state
        try:
            import streamlit as st  # type: ignore
            return st.session_state
        except Exception:
            return {}

    def get(self, key: str, default: Any = None) -> Any:
        state = self._state()
        try:
            return state.get(key, default)
        except Exception:
            try:
                return state[key]
            except Exception:
                return default

    def set(self, key: str, value: Any) -> Any:
        state = self._state()
        try:
            state[key] = value
        except Exception:
            pass
        return value

    def has(self, key: str) -> bool:
        state = self._state()
        try:
            return key in state
        except Exception:
            return False

    def delete(self, key: str) -> None:
        state = self._state()
        try:
            if key in state:
                del state[key]
        except Exception:
            pass

    def get_first(self, keys: Iterable[str], default: Any = None) -> Any:
        for key in keys:
            value = self.get(key, None)
            if value not in (None, "", [], {}):
                return value
        return default

    def snapshot(self, keys: Iterable[str]) -> Dict[str, Any]:
        return {key: self.get(key) for key in keys if self.has(key)}


_default_state_service = StateService()


def get_state_service(session_state: Optional[Any] = None) -> StateService:
    if session_state is not None:
        return StateService(session_state)
    return _default_state_service
