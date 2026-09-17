from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

@dataclass(frozen=True)
class ShellRoute:
    slug: str
    label: str
    module: str

DESKTOP_ROUTES=(ShellRoute("overview","Oversikt","overview"),ShellRoute("portfolio","Porteføljer","portfolio"),ShellRoute("market","Marked","market"),ShellRoute("autonomy","Autonomi","autonomy"),ShellRoute("reports","Rapporter","reports"),ShellRoute("operations","Drift","operations"))
MOBILE_ROUTES=(ShellRoute("overview","Oversikt","overview"),ShellRoute("portfolio","Portefølje","portfolio"),ShellRoute("market","Marked","market"),ShellRoute("alerts","Varsler","operations"),ShellRoute("more","Mer","overview"))
_ALIASES={"paper":"portfolio","paper_trading":"portfolio","super_portfolio":"portfolio","long_engine":"market","analysis":"market","top_picks":"market","control_center":"overview","system":"operations","jobs":"operations","approvals":"autonomy"}
_LEGACY_TARGETS={"overview":"dashboard","portfolio":"portfolio","market":"long_engine","autonomy":"autonomy","reports":"reports","operations":"operations","alerts":"alerts","more":"system"}

def canonical_shell_route(value: str) -> str:
    slug=str(value or "overview").strip().lower().replace("-","_")
    return _ALIASES.get(slug,slug if slug in {r.slug for r in DESKTOP_ROUTES}|{"alerts","more"} else "overview")

def use_v2_shell() -> bool:
    return os.getenv("AA_UI_SHELL_V2","1").strip().lower() not in {"0","false","no","off"}

def render_shell(st_module, route: str, status: Mapping[str,Any] | None = None) -> str:
    current=canonical_shell_route(route); status=status or {}
    def nav_html(routes,css):
        links=[]
        for item in routes:
            active=' aria-current="page"' if item.slug==current else ""
            target=_LEGACY_TARGETS[item.slug]
            links.append(f'<a href="?aa_nav={target}" class="aa-ui-nav-link aa-module-{item.module}"{active}>{item.label}</a>')
        return f'<nav class="{css}" aria-label="Hovednavigasjon">{"".join(links)}</nav>'
    st_module.markdown(nav_html(DESKTOP_ROUTES,"aa-desktop-nav"),unsafe_allow_html=True)
    st_module.markdown(nav_html(MOBILE_ROUTES,"aa-mobile-nav"),unsafe_allow_html=True)
    return current
