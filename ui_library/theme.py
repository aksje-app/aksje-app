from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class UITokens:
    radius_sm: int = 8
    radius_md: int = 12
    radius_lg: int = 16
    spacing_xs: str = ".25rem"
    spacing_sm: str = ".5rem"
    spacing_md: str = ".8rem"
    spacing_lg: str = "1.15rem"
    text_muted: str = "#94a3b8"
    text_primary: str = "#e5e7eb"
    border: str = "rgba(148,163,184,.30)"
    surface: str = "rgba(15,23,42,.72)"
    surface_soft: str = "rgba(30,41,59,.58)"
    success: str = "#22c55e"
    warning: str = "#f59e0b"
    danger: str = "#ef4444"
    info: str = "#38bdf8"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


UI_TOKENS = UITokens()

@dataclass(frozen=True)
class ModuleTheme:
    name: str
    accent: str
    accent_soft: str
    aurora: str

_MODULE_THEMES = {
    "overview": ModuleTheme("overview", "#d6b36a", "rgba(214,179,106,.14)", "rgba(45,212,191,.10)"),
    "portfolio": ModuleTheme("portfolio", "#45c7ad", "rgba(69,199,173,.14)", "rgba(45,212,191,.13)"),
    "market": ModuleTheme("market", "#5aa7ff", "rgba(90,167,255,.14)", "rgba(59,130,246,.13)"),
    "reports": ModuleTheme("reports", "#d6b36a", "rgba(214,179,106,.14)", "rgba(245,158,11,.10)"),
    "autonomy": ModuleTheme("autonomy", "#9b87f5", "rgba(155,135,245,.14)", "rgba(139,92,246,.11)"),
    "operations": ModuleTheme("operations", "#8fa7bd", "rgba(143,167,189,.14)", "rgba(14,165,233,.08)"),
}

def module_theme(name: str) -> ModuleTheme:
    return _MODULE_THEMES.get(str(name or "").lower(), _MODULE_THEMES["overview"])

def css_variables(theme: ModuleTheme) -> str:
    return (":root{--aa-bg:#06111f;--aa-surface:#0b1b2d;"
            f"--aa-aurora:{theme.aurora};--aa-accent:{theme.accent};--aa-accent-soft:{theme.accent_soft};"
            "--aa-focus:#f4cc78;--aa-text:#edf4fb;--aa-muted:#91a4b7;}")


def inject_design_system(st_module, module: str = "overview") -> None:
    """Inject one late, scoped CSS layer used by shared components.

    The selectors only target ``aa-ui-*`` classes. Existing legacy CSS remains
    untouched, which keeps this migration low-risk.
    """
    t = UI_TOKENS
    theme = module_theme(module)
    st_module.markdown(
        f"""
<style id="aa-ui-design-system-v18683">
{css_variables(theme)}
.aa-shell{{min-height:100vh;color:var(--aa-text);background:radial-gradient(circle at 82% 5%,var(--aa-aurora),transparent 32%);}}
.aa-ui-hero{{border:1px solid {t.border};border-radius:20px;padding:1rem 1.1rem;background:linear-gradient(135deg,var(--aa-accent-soft),rgba(11,27,45,.9));box-shadow:0 16px 40px rgba(0,0,0,.18);}}
.aa-ui-hero h1{{font-size:clamp(1.35rem,2vw,2rem);margin:0;color:var(--aa-text);}} .aa-ui-hero p{{color:#cbd5e1;margin:.35rem 0 0;}}
.aa-ui-decision-grid,.aa-ui-metric-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:.7rem;margin:.65rem 0;}}
.aa-ui-decision-card,.aa-ui-metric-card,.aa-ui-timeline-step,.aa-ui-ambient{{border:1px solid {t.border};border-radius:14px;background:rgba(11,27,45,.86);padding:.8rem;min-width:0;}}
.aa-ui-decision-action{{font-size:.72rem;font-weight:900;letter-spacing:.08em;color:var(--aa-accent);}} .aa-ui-decision-ticker{{font-size:1.08rem;font-weight:900;}}
.aa-ui-timeline{{display:grid;gap:.55rem}} .aa-ui-timeline-step{{border-left:4px solid var(--aa-accent)}}
.aa-mobile-nav,.aa-desktop-nav{{display:none}}
.aa-ui-nav-link{{display:flex;align-items:center;justify-content:center;min-height:44px;padding:.3rem;color:var(--aa-text)!important;text-decoration:none!important;font-size:.72rem;font-weight:800;border-radius:9px;}}
.aa-ui-nav-link[aria-current="page"]{{background:var(--aa-accent-soft);box-shadow:inset 0 0 0 1px var(--aa-accent);}}
.aa-ui-page-state.tone-danger{{border-color:{t.danger}}}
.aa-shell button,.aa-shell a[role="button"]{{min-height:44px}}
.aa-shell :focus-visible{{outline:3px solid var(--aa-focus)!important;outline-offset:2px!important}}
.aa-ui-page-header{{margin:.15rem 0 .75rem;padding:.05rem 0;}}
.aa-ui-page-title{{font-size:1.34rem;font-weight:900;line-height:1.18;color:{t.text_primary};}}
.aa-ui-page-subtitle{{margin-top:.2rem;color:{t.text_muted};font-size:.9rem;line-height:1.35;}}
.aa-ui-section-header{{margin:.65rem 0 .35rem;font-size:1.02rem;font-weight:850;color:{t.text_primary};}}
.aa-ui-banner{{border:1px solid {t.border};border-left:5px solid var(--aa-accent,{t.info});border-radius:{t.radius_md}px;padding:.62rem .75rem;background:{t.surface};margin:.35rem 0 .65rem;}}
.aa-ui-banner-title{{font-weight:850;color:{t.text_primary};}}
.aa-ui-banner-body{{color:#cbd5e1;font-size:.88rem;margin-top:.12rem;}}
.aa-ui-status-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:.45rem;margin:.35rem 0 .65rem;}}
.aa-ui-status-item{{border:1px solid {t.border};border-radius:{t.radius_sm}px;background:{t.surface_soft};padding:.5rem .62rem;min-width:0;}}
.aa-ui-status-label{{color:{t.text_muted};font-size:.74rem;text-transform:uppercase;letter-spacing:.035em;font-weight:800;}}
.aa-ui-status-value{{color:{t.text_primary};font-size:.93rem;font-weight:850;overflow-wrap:anywhere;}}
.aa-ui-badge{{display:inline-flex;align-items:center;gap:.28rem;border-radius:999px;padding:.16rem .48rem;font-size:.76rem;font-weight:850;border:1px solid currentColor;background:rgba(15,23,42,.48);}}
.aa-ui-empty{{border:1px dashed {t.border};border-radius:{t.radius_md}px;padding:.9rem;text-align:center;color:{t.text_muted};background:rgba(15,23,42,.28);}}
.aa-ui-kpi-label{{font-size:.76rem;color:{t.text_muted};font-weight:750;}}
.aa-ui-kpi-value{{font-size:1.13rem;color:{t.text_primary};font-weight:900;line-height:1.15;}}
.aa-ui-kpi-delta{{font-size:.76rem;color:#cbd5e1;margin-top:.12rem;}}
@media (max-width:1100px){{.aa-ui-status-grid{{grid-template-columns:repeat(2,minmax(0,1fr));}}}}
@media (max-width:760px){{.aa-ui-decision-grid,.aa-ui-metric-grid,.aa-ui-status-grid{{grid-template-columns:1fr}}.aa-mobile-nav{{display:grid;grid-template-columns:repeat(5,1fr);position:fixed;z-index:999;left:0;right:0;bottom:0;padding:.3rem .25rem calc(.3rem + env(safe-area-inset-bottom));background:#071524;border-top:1px solid {t.border}}}.aa-shell{{padding-bottom:74px}}}}
@media (prefers-reduced-motion:reduce){{.aa-shell *{{scroll-behavior:auto!important;animation-duration:.01ms!important;transition-duration:.01ms!important}}}}
</style>
        """,
        unsafe_allow_html=True,
    )
