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
import logging

from typing import Any, Dict, Iterable, Optional


class StateService:
    def __init__(self, session_state: Optional[Any] = None):
        self.session_state = session_state

    def _state(self) -> Any:
        if self.session_state is not None:
            return self.session_state
        # RC15: report/scheduler workers are intentionally UI-free. Importing
        # Streamlit from those threads creates ``missing ScriptRunContext``
        # warnings and can accidentally couple analysis to a browser session.
        try:
            from background_execution import is_background_execution
            if is_background_execution():
                return {}
        except Exception:
            pass
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
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)
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
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)

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
