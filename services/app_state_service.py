from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Iterable, Optional

from core_architecture import AppState, AppStateStore
from services.state_service import StateService, get_state_service


LEGACY_KEY_MAP = {
    "aa_nav": ("navigation", "main_area"),
    "aa_group": ("navigation", "group"),
    "aa_panel": ("navigation", "panel"),
    "aa_tab": ("navigation", "tab"),
    "aa_subtab": ("navigation", "subtab"),
    "paper_manual_override_state_v18674a": ("paper_trading", "manual_override"),
    "paper_active_tab_v18674c": ("paper_trading", "selected_tab"),
    "paper_stock_buy_symbol_v1871": ("paper_trading", "active_symbol"),
}


class AppStateService:
    """Typed state facade with backwards-compatible legacy-key migration.

    Existing Streamlit keys remain operational. New code can use one typed
    AppState while migration mirrors values in both directions.
    """

    def __init__(self, state_service: Optional[StateService] = None):
        self.state_service = state_service or get_state_service()

    def _session(self) -> Any:
        return self.state_service._state()

    def load(self, migrate: bool = True) -> AppState:
        state = AppStateStore.load(self._session())
        if migrate:
            self.migrate_legacy_keys(state)
        return state

    def save(self, state: AppState, mirror_legacy: bool = True) -> AppState:
        AppStateStore.save(self._session(), state)
        if mirror_legacy:
            self.mirror_to_legacy_keys(state)
        return state

    def migrate_legacy_keys(self, state: Optional[AppState] = None) -> AppState:
        state = state or AppStateStore.load(self._session())
        for legacy_key, (section_name, attr_name) in LEGACY_KEY_MAP.items():
            value = self.state_service.get(legacy_key, None)
            if value in (None, ""):
                continue
            section = getattr(state, section_name)
            current = getattr(section, attr_name)
            if current in (None, "", "OFF", "Handel") or legacy_key.startswith("aa_"):
                setattr(section, attr_name, str(value))
        AppStateStore.save(self._session(), state)
        return state

    def mirror_to_legacy_keys(self, state: Optional[AppState] = None) -> None:
        state = state or AppStateStore.load(self._session())
        for legacy_key, (section_name, attr_name) in LEGACY_KEY_MAP.items():
            value = getattr(getattr(state, section_name), attr_name)
            if value not in (None, ""):
                self.state_service.set(legacy_key, value)

    def update_navigation(self, **values: str) -> AppState:
        state = self.load()
        for key, value in values.items():
            if hasattr(state.navigation, key) and value is not None:
                setattr(state.navigation, key, str(value))
        return self.save(state)

    def update_paper_trading(self, **values: str) -> AppState:
        state = self.load()
        for key, value in values.items():
            if hasattr(state.paper_trading, key) and value is not None:
                setattr(state.paper_trading, key, str(value))
        return self.save(state)

    def snapshot(self) -> Dict[str, Any]:
        return asdict(self.load())


_default_app_state_service: Optional[AppStateService] = None


def get_app_state_service(session_state: Optional[Any] = None) -> AppStateService:
    global _default_app_state_service
    if session_state is not None:
        return AppStateService(get_state_service(session_state))
    if _default_app_state_service is None:
        _default_app_state_service = AppStateService()
    return _default_app_state_service
