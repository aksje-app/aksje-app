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


def inject_design_system(st_module) -> None:
    """Inject one late, scoped CSS layer used by shared components.

    The selectors only target ``aa-ui-*`` classes. Existing legacy CSS remains
    untouched, which keeps this migration low-risk.
    """
    t = UI_TOKENS
    st_module.markdown(
        f"""
<style id="aa-ui-design-system-v18683">
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
</style>
        """,
        unsafe_allow_html=True,
    )
