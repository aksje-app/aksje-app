from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional, Tuple

from trading_settings import DEFAULT_RULES, load_rules, save_rules


class TradingRuleService:
    """Single entry point for Paper Trading rule reads and writes."""

    def load(self) -> Dict[str, Any]:
        data = load_rules() or {}
        merged = deepcopy(DEFAULT_RULES)
        merged.update(data)
        return merged

    def update(self, changes: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        rules = self.load()
        allowed = set(DEFAULT_RULES) | set(rules)
        invalid = sorted(set(changes) - allowed)
        if invalid:
            return False, f"Ukjente regler: {', '.join(invalid)}", rules
        rules.update(changes)
        save_rules(rules)
        return True, "Regler lagret", rules

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        return self.load().get(key, default)


_default_trading_rule_service = TradingRuleService()


def get_trading_rule_service() -> TradingRuleService:
    return _default_trading_rule_service
