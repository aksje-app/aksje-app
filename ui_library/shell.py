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
MORE_ROUTES=(
    ShellRoute("autonomy","Autonomi","autonomy"),
    ShellRoute("reports","Rapporter","reports"),
    ShellRoute("jobs","Jobber/planlegger","operations"),
    ShellRoute("approvals","Godkjenninger","autonomy"),
    ShellRoute("paper","Paper Trading","portfolio"),
    ShellRoute("fx_alerts","Valuta","market"),
    ShellRoute("operations","Drift","operations"),
    ShellRoute("settings","Innstillinger","operations"),
)
_ALIASES={"paper":"portfolio","paper_trading":"portfolio","super_portfolio":"portfolio","long_engine":"market","analysis":"market","top_picks":"market","control_center":"overview","system":"operations","settings":"operations","jobs":"operations","approvals":"autonomy","fx_alerts":"market","drift_center":"operations"}
_LEGACY_TARGETS={"overview":"dashboard","portfolio":"portfolio","market":"market","autonomy":"autonomy","reports":"reports","operations":"drift_center","alerts":"alerts","more":"system","jobs":"jobs","approvals":"approvals","paper":"paper_trading","fx_alerts":"fx_alerts","settings":"system"}
_NAV_ICONS={"overview":"⌂","portfolio":"▣","market":"⌁","alerts":"!","more":"•••","autonomy":"◈","reports":"▤","jobs":"◷","approvals":"✓","paper":"◇","fx_alerts":"¤","operations":"⚙","settings":"⚙"}

def canonical_shell_route(value: str) -> str:
    slug=str(value or "overview").strip().lower().replace("-","_")
    return _ALIASES.get(slug,slug if slug in {r.slug for r in DESKTOP_ROUTES}|{"alerts","more"} else "overview")

def use_v2_shell() -> bool:
    # Aurora is the production shell after PR #15. The old rollout flag may
    # still exist as ``0`` on long-lived Render services, which previously
    # made production silently fall back to the legacy dashboard even though
    # main contained the new UI. Keep the flag outside production for local
    # rollback/testing, but make the deployed UI deterministic.
    if os.getenv("APP_ENVIRONMENT", "").strip().lower() == "production":
        return True
    return os.getenv("AA_UI_SHELL_V2","1").strip().lower() not in {"0","false","no","off"}

def render_shell(st_module, route: str, status: Mapping[str,Any] | None = None) -> str:
    current=canonical_shell_route(route); status=status or {}
    def nav_link(item: ShellRoute, *, mobile: bool = False) -> str:
        active=' aria-current="page"' if item.slug==current else ""
        target=_LEGACY_TARGETS[item.slug]
        icon=(f'<span class="aa-nav-icon" aria-hidden="true">{_NAV_ICONS.get(item.slug, "•")}</span>' if mobile else "")
        return f'<a href="?aa_nav={target}" class="aa-ui-nav-link aa-module-{item.module}"{active}>{icon}<span>{item.label}</span></a>'
    def nav_html(routes,css):
        links=[]
        for item in routes:
            links.append(nav_link(item))
        return f'<nav class="{css}" aria-label="Hovednavigasjon">{"".join(links)}</nav>'
    def mobile_nav_html() -> str:
        primary=[]
        for item in MOBILE_ROUTES:
            if item.slug != "more":
                primary.append(nav_link(item, mobile=True))
                continue
            more_active = current in {"autonomy", "reports", "operations"}
            active = ' aria-current="page"' if more_active else ""
            more_links="".join(nav_link(extra, mobile=True) for extra in MORE_ROUTES)
            primary.append(
                '<details class="aa-mobile-more">'
                f'<summary class="aa-ui-nav-link"{active}>'
                f'<span class="aa-nav-icon" aria-hidden="true">{_NAV_ICONS["more"]}</span><span>Mer</span></summary>'
                '<div class="aa-mobile-more-panel" role="dialog" aria-label="Flere programområder">'
                '<header><strong>Flere områder</strong><small>Velg området du vil åpne</small></header>'
                f'<div class="aa-mobile-more-grid">{more_links}</div></div></details>'
            )
        return f'<nav class="aa-mobile-nav" aria-label="Mobil hovednavigasjon">{"".join(primary)}</nav>'
    st_module.markdown(nav_html(DESKTOP_ROUTES,"aa-desktop-nav"),unsafe_allow_html=True)
    st_module.markdown(mobile_nav_html(),unsafe_allow_html=True)
    return current
