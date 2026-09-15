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
.aa-mobile-nav{{display:none}} .aa-desktop-nav{{display:grid;grid-template-columns:repeat(6,minmax(110px,1fr));gap:.3rem;margin:.25rem 0 1rem;padding:.35rem;border:1px solid rgba(111,145,175,.34);border-radius:16px;background:rgba(11,25,41,.88);box-shadow:0 12px 34px rgba(0,0,0,.16)}}
.aa-ui-nav-link{{display:flex;align-items:center;justify-content:center;min-height:44px;padding:.3rem;color:var(--aa-text)!important;text-decoration:none!important;font-size:.72rem;font-weight:800;border-radius:9px;}}
.aa-ui-nav-link{{position:relative;color:#91a4b7!important;letter-spacing:.025em}} .aa-ui-nav-link:hover{{color:#edf4fb!important;background:rgba(143,167,189,.08)}} .aa-ui-nav-link[aria-current="page"]{{color:#f2d17f!important;background:rgba(214,179,106,.08);box-shadow:none}} .aa-ui-nav-link[aria-current="page"]:after{{content:"";position:absolute;left:22%;right:22%;bottom:2px;height:3px;border-radius:3px;background:#d6b36a}}
.aa-ui-page-state.tone-danger{{border-color:{t.danger}}}
.aa-shell button,.aa-shell a[role="button"]{{min-height:44px}}
.aa-shell :focus-visible{{outline:3px solid var(--aa-focus)!important;outline-offset:2px!important}}
.aa-overview-hero{{position:relative;display:grid;grid-template-columns:minmax(0,1.7fr) auto;gap:1rem;align-items:start;padding:2rem 2.1rem;margin:.35rem 0 1.1rem;border:1px solid rgba(111,145,175,.34);border-radius:22px;overflow:hidden;background:radial-gradient(ellipse at 82% 45%,rgba(63,184,163,.18),transparent 28%),linear-gradient(125deg,rgba(11,28,45,.98),rgba(7,25,38,.96));box-shadow:0 24px 65px rgba(0,0,0,.22)}}
.aa-overview-hero:after{{content:"";position:absolute;width:420px;height:170px;right:-35px;bottom:-95px;border-radius:50%;border-top:1px solid rgba(87,211,188,.48);box-shadow:0 -18px 50px rgba(87,211,188,.08);transform:rotate(-8deg)}}
.aa-overview-hero h1{{margin:.45rem 0 .15rem;font-size:clamp(1.65rem,2.25vw,2.45rem);line-height:1.08;color:#f7fbff}} .aa-overview-hero p{{margin:.35rem 0 1rem;color:#a9bac9;font-size:.9rem}}
.aa-overline,.aa-next-event span,.aa-overview-metric span{{display:block;color:#84a0b7;font-size:.7rem;font-weight:900;letter-spacing:.09em;text-transform:uppercase}}
.aa-market-pill{{display:inline-flex;padding:.55rem 1rem;border:1px solid rgba(87,211,188,.42);border-radius:999px;color:#91d7c8;background:rgba(27,89,79,.18);font-size:.78rem;letter-spacing:.035em}} .aa-system-chip{{position:relative;z-index:2;display:flex;align-items:center;gap:.55rem;padding:.65rem 1rem;border:1px solid rgba(87,211,188,.48);border-radius:999px;color:#5ed4ba;background:rgba(20,90,78,.24);font-size:.8rem;font-weight:950;letter-spacing:.025em}} .aa-system-chip i{{width:9px;height:9px;border-radius:50%;background:#5ed4ba;box-shadow:0 0 18px rgba(94,212,186,.7)}}
.aa-next-event{{padding:.85rem 1rem;border:1px solid rgba(214,179,106,.35);border-radius:14px;background:rgba(6,17,31,.55)}} .aa-next-event strong,.aa-next-event small{{display:block}} .aa-next-event strong{{margin:.18rem 0;color:#f3d58e;font-size:1rem}} .aa-next-event small{{color:#9fb0c0}}
.aa-overview-metric{{min-height:108px;padding:.85rem 1rem;margin:0 0 1rem;border:1px solid rgba(143,167,189,.24);border-radius:15px;background:linear-gradient(145deg,rgba(12,29,47,.95),rgba(7,20,34,.95))}} .aa-overview-metric strong{{display:block;margin:.25rem 0;color:#f4f8fc;font-size:1.45rem}} .aa-overview-metric small{{color:#91a4b7}}
.aa-portfolio-command{{position:relative;display:grid;grid-template-columns:minmax(0,1.75fr) minmax(230px,.72fr);gap:1rem;align-items:stretch;margin:.2rem 0 .55rem}} .aa-portfolio-command>article{{position:relative;min-height:204px;border:1px solid rgba(111,145,175,.46);border-radius:18px;background:linear-gradient(145deg,rgba(16,33,51,.96),rgba(11,25,41,.96));padding:1.15rem 1.3rem;overflow:hidden}}
.aa-portfolio-value>span,.aa-confidence>span{{display:block;color:#9aaabd;font-size:.7rem;font-weight:900;letter-spacing:.06em}} .aa-portfolio-value>p,.aa-confidence>p{{margin:.2rem 0;color:#71869a;font-size:.68rem;line-height:1.35}} .aa-portfolio-value>strong{{display:block;margin:.8rem 0 0;color:#f4f7fb;font-size:clamp(1.7rem,2.65vw,2.7rem);line-height:1}} .aa-portfolio-value>b{{display:block;margin:.3rem 0;color:#58d3b5;font-size:1rem}} .aa-portfolio-value>b small{{color:#8799ab;font-weight:650;font-size:.72rem}}
.aa-chart-wrap{{position:absolute;left:35%;right:1.3rem;bottom:.55rem;height:92px;padding-left:34px}} .aa-chart-wrap>span{{display:block;margin:0 0 -.1rem;color:#71869a;font-size:.57rem;font-weight:900;letter-spacing:.08em}} .aa-return-chart{{display:block;width:100%!important;height:68px!important;overflow:visible}} .aa-chart-baseline{{stroke:rgba(143,167,189,.25);stroke-width:1;stroke-dasharray:4 5;vector-effect:non-scaling-stroke}} .aa-chart-area{{fill:url(#aaReturnFill)}} .aa-chart-line{{fill:none;stroke:#55d5ba;stroke-width:2.25;stroke-linecap:round;stroke-linejoin:round;vector-effect:non-scaling-stroke}} .aa-chart-end{{fill:#dfc06c;stroke:#102235;stroke-width:2;vector-effect:non-scaling-stroke;filter:drop-shadow(0 0 4px rgba(223,192,108,.55))}} .aa-axis-y{{position:absolute;left:0;top:16px;bottom:14px;display:flex;flex-direction:column;justify-content:space-between;color:#71869a;font-size:.52rem}} .aa-axis-y b,.aa-axis-x b{{font-weight:750}} .aa-axis-x{{display:flex;justify-content:space-between;margin:-.2rem 0 0;color:#71869a;font-size:.52rem}} .aa-chart-empty{{position:absolute;left:1.3rem;bottom:1.1rem;color:#75899d;font-size:.72rem}}
.aa-confidence{{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}} .aa-confidence>strong{{font-size:2.55rem;line-height:1;color:#f4f7fb;margin:.3rem 0 .15rem}} .aa-confidence>small{{color:#e0c171;font-size:.68rem;font-weight:900;letter-spacing:.04em}} .aa-confidence-components{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.28rem;width:100%;margin-top:.65rem;padding-top:.55rem;border-top:1px solid rgba(143,167,189,.18)}} .aa-confidence-components>div{{padding:.25rem;border-radius:8px;background:rgba(6,17,31,.42)}} .aa-confidence-components span,.aa-confidence-components strong{{display:block}} .aa-confidence-components span{{color:#7f92a5;font-size:.56rem;font-weight:800;text-transform:uppercase}} .aa-confidence-components strong{{color:#dce7f1;font-size:.84rem}} .aa-confidence-empty{{margin:.25rem 0;color:#7f92a5;font-size:.68rem;line-height:1.35}}
.aa-portfolio-facts{{display:grid;grid-template-columns:repeat(3,1fr);margin:.2rem 0 1.2rem}} .aa-portfolio-facts>div{{padding:.55rem 1rem;border-right:1px solid rgba(111,145,175,.3)}} .aa-portfolio-facts>div:last-child{{border:0}} .aa-portfolio-facts strong,.aa-portfolio-facts span{{display:block}} .aa-portfolio-facts strong{{font-size:1.3rem;color:#eff5fb}} .aa-portfolio-facts span{{font-size:.66rem;color:#7f92a5;font-weight:900}}
.aa-decisions-title{{margin-top:1.4rem!important}} .aa-decision-row{{display:grid;grid-template-columns:1fr 120px 110px;gap:.8rem;align-items:center;min-height:76px;padding:.75rem 1rem;margin:.55rem 0;border:1px solid rgba(111,145,175,.36);border-left:7px solid #dcbc65;border-radius:14px;background:rgba(14,29,46,.88)}} .aa-decision-row.tone-success{{border-left-color:#53d2b3}} .aa-decision-row.tone-danger{{border-left-color:#ff7486}} .aa-decision-row>div strong,.aa-decision-row>div small,.aa-decision-row>div b,.aa-decision-row>div em{{display:block}} .aa-decision-row>div strong{{font-size:1.12rem;color:#f1f5f9}} .aa-decision-row>div small{{color:#8da0b3}} .aa-decision-row>div b{{color:#a9b7c7}} .aa-decision-row>div em{{color:#58d3b5;font-style:normal;font-weight:850}} .aa-decision-row>span{{padding:.65rem;text-align:center;border-radius:11px;background:#dfc06c;color:#07111d;font-weight:950}} .aa-decision-row.tone-success>span{{background:#58d3b5}} .aa-decision-row.tone-danger>span{{background:#ff7486}}
.aa-empty-decisions{{padding:1rem;border:1px dashed rgba(111,145,175,.4);border-radius:14px;background:rgba(14,29,46,.5)}} .aa-empty-decisions strong{{color:#eef4fa}} .aa-empty-decisions p{{margin:.2rem 0 0;color:#8fa0b2}}
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
@media (max-width:760px){{.aa-ui-decision-grid,.aa-ui-metric-grid,.aa-ui-status-grid{{grid-template-columns:1fr}}.aa-desktop-nav{{display:none}}.aa-mobile-nav{{display:grid;grid-template-columns:repeat(5,1fr);position:fixed;z-index:999;left:0;right:0;bottom:0;padding:.3rem .25rem calc(.3rem + env(safe-area-inset-bottom));background:#071524;border-top:1px solid {t.border}}}.aa-shell{{padding-bottom:74px}}}}
@media (max-width:760px){{.aa-overview-hero,.aa-portfolio-command{{grid-template-columns:1fr;padding:1rem}}.aa-overview-hero{{padding:1.35rem}}.aa-system-chip{{justify-self:start}}.aa-next-event{{margin-top:.2rem}}.aa-overview-metric{{min-height:88px}}.aa-portfolio-command{{padding:0}}.aa-portfolio-command>article{{min-height:0}}.aa-portfolio-value{{min-height:260px!important}}.aa-confidence{{min-height:210px!important}}.aa-portfolio-value>strong{{margin-top:1rem;font-size:2.15rem}}.aa-chart-wrap{{left:1rem;right:1rem;bottom:.65rem}}.aa-portfolio-facts{{grid-template-columns:1fr}}.aa-portfolio-facts>div{{border-right:0;border-bottom:1px solid rgba(111,145,175,.24)}}.aa-portfolio-facts strong{{font-size:1.15rem}}.aa-decision-row{{grid-template-columns:1fr auto}}.aa-decision-row>span{{grid-column:1/-1}}.st-key-aa_overview_reports button,.st-key-aa_overview_portfolio button,.st-key-aa_overview_market button,.st-key-aa_overview_operations button{{min-height:46px!important}}}}
@media (prefers-reduced-motion:reduce){{.aa-shell *{{scroll-behavior:auto!important;animation-duration:.01ms!important;transition-duration:.01ms!important}}}}
</style>
        """,
        unsafe_allow_html=True,
    )
