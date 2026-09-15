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
            links.append(f'<a href="?aa_nav={item.slug}" class="aa-ui-nav-link aa-module-{item.module}"{active}>{item.label}</a>')
        return f'<nav class="{css}" aria-label="Hovednavigasjon">{"".join(links)}</nav>'
    chip=str(status.get("label") or status.get("state") or "Klar")
    st_module.markdown(f'<div class="aa-shell aa-module-{current}">{nav_html(DESKTOP_ROUTES,"aa-desktop-nav")}<span class="aa-ui-shell-status">{chip}</span>{nav_html(MOBILE_ROUTES,"aa-mobile-nav")}</div>',unsafe_allow_html=True)
    return current
