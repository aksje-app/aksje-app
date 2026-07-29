from __future__ import annotations

import unittest

from core_architecture import AppStateStore, get_services, initialize_core_runtime
from services.app_state_service import get_app_state_service
from services.review_queue_service import VALID_STATUSES
from services.service_registry import build_service_registry


class ServicesV18681Tests(unittest.TestCase):
    def test_legacy_state_migration(self):
        session = {
            "aa_nav": "Andre paneler",
            "aa_panel": "AI Discovery",
            "paper_manual_override_state_v18674a": "FORCE_ALLOW",
        }
        service = get_app_state_service(session)
        state = service.load(migrate=True)
        self.assertEqual(state.navigation.main_area, "Andre paneler")
        self.assertEqual(state.navigation.panel, "AI Discovery")
        self.assertEqual(state.paper_trading.manual_override, "FORCE_ALLOW")
        self.assertIn(AppStateStore.KEY, session)

    def test_state_mirrors_legacy_keys(self):
        session = {}
        service = get_app_state_service(session)
        state = service.load()
        state.navigation.tab = "Portefølje"
        service.save(state)
        self.assertEqual(session["aa_tab"], "Portefølje")

    def test_registry_contains_current_and_legacy_consolidated_services(self):
        registry = build_service_registry(session_state={})
        self.assertIsNotNone(registry.state)
        self.assertIsNotNone(registry.storage)
        self.assertIsNotNone(registry.persistence)
        self.assertIsNotNone(registry.universe)
        self.assertIsNotNone(registry.paper_trading)

        initialize_core_runtime()
        legacy = get_services()
        for name in ("app_state", "currency", "notifications", "review_queue", "trading_rules"):
            self.assertIsNotNone(legacy.get(name))

    def test_review_status_contract(self):
        self.assertEqual(VALID_STATUSES, {"ÅPEN", "GODKJENT", "AVVIST", "KJØPT"})


if __name__ == "__main__":
    unittest.main()
