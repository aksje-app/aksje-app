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
.aa-overview-hero{{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(240px,.7fr);gap:1rem;align-items:center;padding:1.25rem 1.35rem;margin:.35rem 0 1rem;border:1px solid rgba(143,167,189,.28);border-radius:20px;background:linear-gradient(125deg,rgba(11,31,49,.96),rgba(8,48,52,.82));box-shadow:0 20px 60px rgba(0,0,0,.2)}}
.aa-overview-hero h1{{margin:.15rem 0;font-size:clamp(1.65rem,2.6vw,2.65rem);line-height:1.08;color:#f7fbff}} .aa-overview-hero p{{margin:.35rem 0 0;color:#a9bac9;font-size:1rem}}
.aa-overline,.aa-next-event span,.aa-overview-metric span{{display:block;color:#84a0b7;font-size:.7rem;font-weight:900;letter-spacing:.09em;text-transform:uppercase}}
.aa-next-event{{padding:.85rem 1rem;border:1px solid rgba(214,179,106,.35);border-radius:14px;background:rgba(6,17,31,.55)}} .aa-next-event strong,.aa-next-event small{{display:block}} .aa-next-event strong{{margin:.18rem 0;color:#f3d58e;font-size:1rem}} .aa-next-event small{{color:#9fb0c0}}
.aa-overview-metric{{min-height:108px;padding:.85rem 1rem;margin:0 0 1rem;border:1px solid rgba(143,167,189,.24);border-radius:15px;background:linear-gradient(145deg,rgba(12,29,47,.95),rgba(7,20,34,.95))}} .aa-overview-metric strong{{display:block;margin:.25rem 0;color:#f4f8fc;font-size:1.45rem}} .aa-overview-metric small{{color:#91a4b7}}
.st-key-aa_overview_reports button,.st-key-aa_overview_portfolio button,.st-key-aa_overview_market button,.st-key-aa_overview_operations button{{width:100%!important;min-height:42px!important;margin:0 0 .38rem!important;border-radius:11px!important;justify-content:flex-start!important;padding:.55rem .8rem!important;font-weight:850!important}}
.st-key-aa_overview_reports button{{justify-content:center!important;box-shadow:0 8px 24px rgba(14,165,233,.18)!important}}
.st-key-aa_overview_portfolio,.st-key-aa_overview_market,.st-key-aa_overview_operations{{width:100%!important}}
.aa-section-title{{margin:.4rem 0 .7rem!important;color:#eaf2f9!important;font-size:1rem!important;letter-spacing:.01em}}
.aa-attention-card{{display:grid;grid-template-columns:12px 1fr;gap:.65rem;align-items:start;padding:.8rem .9rem;margin:0 0 .55rem;border:1px solid rgba(143,167,189,.22);border-radius:13px;background:rgba(10,25,42,.76)}} .aa-attention-card strong{{color:#eef5fb}} .aa-attention-card p{{margin:.15rem 0 0;color:#9eafbf;font-size:.85rem;line-height:1.4}} .aa-attention-dot{{width:9px;height:9px;margin-top:.32rem;border-radius:50%;background:#5aa7ff;box-shadow:0 0 0 4px rgba(90,167,255,.1)}}
.aa-attention-card.tone-danger .aa-attention-dot{{background:#ef4444}} .aa-attention-card.tone-warning .aa-attention-dot{{background:#d6b36a}} .aa-attention-card.tone-success .aa-attention-dot{{background:#45c7ad}}
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
@media (max-width:760px){{.aa-overview-hero{{grid-template-columns:1fr;padding:1rem}}.aa-next-event{{margin-top:.2rem}}.aa-overview-metric{{min-height:88px}}.st-key-aa_overview_reports button,.st-key-aa_overview_portfolio button,.st-key-aa_overview_market button,.st-key-aa_overview_operations button{{min-height:46px!important}}}}
@media (prefers-reduced-motion:reduce){{.aa-shell *{{scroll-behavior:auto!important;animation-duration:.01ms!important;transition-duration:.01ms!important}}}}
</style>
        """,
        unsafe_allow_html=True,
    )
