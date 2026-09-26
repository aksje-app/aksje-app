from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

@dataclass(frozen=True)
class ShellRoute:
    slug: str
    label: str
    module: str

DESKTOP_ROUTES=(ShellRoute("overview","Oversikt","overview"),ShellRoute("portfolio","Porteføljer","portfolio"),ShellRoute("market","Marked","market"),ShellRoute("quality","Kvalitet","market"),ShellRoute("autonomy","Autonomi","autonomy"),ShellRoute("reports","Rapporter","reports"),ShellRoute("operations","Drift","operations"))
MOBILE_ROUTES=(ShellRoute("overview","Oversikt","overview"),ShellRoute("portfolio","Portefølje","portfolio"),ShellRoute("market","Marked","market"),ShellRoute("quality","Kvalitet","market"),ShellRoute("alerts","Varsler","operations"),ShellRoute("more","Mer","overview"))
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
_ALIASES={"paper":"portfolio","paper_trading":"portfolio","super_portfolio":"portfolio","long_engine":"market","analysis":"market","top_picks":"market","quality_valuation":"quality","control_center":"overview","system":"operations","settings":"operations","jobs":"operations","approvals":"autonomy","fx_alerts":"market","drift_center":"operations"}
_LEGACY_TARGETS={"overview":"dashboard","portfolio":"portfolio","market":"market","quality":"quality_valuation","autonomy":"autonomy","reports":"reports","operations":"drift_center","alerts":"alerts","more":"system","jobs":"jobs","approvals":"approvals","paper":"paper_trading","fx_alerts":"fx_alerts","settings":"system"}
_NAV_ICONS={"overview":"⌂","portfolio":"▣","market":"⌁","quality":"◆","alerts":"!","more":"•••","autonomy":"◈","reports":"▤","jobs":"◷","approvals":"✓","paper":"◇","fx_alerts":"¤","operations":"⚙","settings":"⚙"}

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

    def _navigate(target: str) -> None:
        st_module.query_params["aa_nav"] = target
        try:
            st_module.rerun()
        except Exception:
            pass

    def nav_link(item: ShellRoute, *, mobile: bool = False) -> str:
        active=' aria-current="page"' if item.slug==current else ""
        target=_LEGACY_TARGETS[item.slug]
        icon=(f'<span class="aa-nav-icon" aria-hidden="true">{_NAV_ICONS.get(item.slug, "•")}</span>' if mobile else "")
        return f'<a href="?aa_nav={target}" target="_self" class="aa-ui-nav-link aa-module-{item.module}"{active}>{icon}<span>{item.label}</span></a>'

    def nav_html(routes,css):
        return f'<nav class="{css}" aria-label="Hovednavigasjon">{"".join(nav_link(item) for item in routes)}</nav>'

    # Desktop keeps normal links. Mobile uses native Streamlit buttons because
    # fixed HTML descendants are not reliably hit-testable in iOS Safari/WebView.
    st_module.markdown(nav_html(DESKTOP_ROUTES,"aa-desktop-nav"),unsafe_allow_html=True)

    if not all(hasattr(st_module, name) for name in ("container","columns","button","session_state","query_params")):
        # Test/compatibility fallback only.
        st_module.markdown(
            f'<nav class="aa-mobile-nav" aria-label="Mobil hovednavigasjon">{"".join(nav_link(item, mobile=True) for item in MOBILE_ROUTES)}</nav>',
            unsafe_allow_html=True,
        )
        return current

    with st_module.container(key="aa_mobile_nav_native"):
        cols=st_module.columns(len(MOBILE_ROUTES), gap="small")
        for col,item in zip(cols,MOBILE_ROUTES):
            with col:
                label=f'{_NAV_ICONS.get(item.slug, "•")}\\n{item.label}'
                if item.slug == "more":
                    if st_module.button(label, key="aa_mobile_nav_more", use_container_width=True):
                        st_module.session_state["aa_mobile_more_open"] = not bool(st_module.session_state.get("aa_mobile_more_open"))
                        st_module.rerun()
                elif st_module.button(label, key=f"aa_mobile_nav_{item.slug}", use_container_width=True):
                    _navigate(_LEGACY_TARGETS[item.slug])

    if st_module.session_state.get("aa_mobile_more_open"):
        with st_module.container(key="aa_mobile_more_native"):
            st_module.markdown("**Flere områder**")
            extra_cols=st_module.columns(2, gap="small")
            for idx,item in enumerate(MORE_ROUTES):
                with extra_cols[idx % 2]:
                    if st_module.button(item.label, key=f"aa_mobile_more_{item.slug}", use_container_width=True):
                        st_module.session_state["aa_mobile_more_open"] = False
                        _navigate(_LEGACY_TARGETS[item.slug])
            if st_module.button("Lukk", key="aa_mobile_more_close", use_container_width=True):
                st_module.session_state["aa_mobile_more_open"] = False
                st_module.rerun()
    return current
