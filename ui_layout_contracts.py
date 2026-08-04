"""Pure presentation helpers used by Streamlit and visual regression probes.

The functions in this module deliberately have no Streamlit dependency.  This
lets release tests render the same HTML at mobile/tablet/desktop widths without
starting the full application.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Iterable, Mapping, Sequence


def format_decimal(value: object, decimals: int = 2, *, decimal_comma: bool = True, fallback: str = "-") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    text = f"{number:.{max(0, int(decimals))}f}"
    return text.replace(".", ",") if decimal_comma else text


def format_percent(value: object, decimals: int = 2, *, signed: bool = False, fallback: str = "-") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    sign = "+" if signed and number > 0 else ""
    return f"{sign}{format_decimal(number, decimals)} %"


def currency_status_css() -> str:
    return """
<style>
.fx-status-grid-v19220rc8 {
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
  gap:.72rem;
  margin:.30rem 0 .85rem 0;
  align-items:stretch;
}
.fx-status-card-v19220rc8 {
  min-width:0;
  border:1px solid rgba(145,166,200,.38);
  border-radius:14px;
  padding:.80rem .86rem;
  background:rgba(11,24,44,.45);
  overflow:hidden;
}
.fx-status-label-v19220rc8 {
  font-size:.76rem;
  color:#aebbd0;
  margin:0 0 .36rem 0;
  white-space:normal;
  line-height:1.25;
}
.fx-status-value-v19220rc8 {
  font-size:1.04rem;
  font-weight:750;
  color:#f4f7fb;
  overflow-wrap:anywhere;
  word-break:normal;
  line-height:1.25;
  margin:0;
}
.fx-status-sub-v19220rc8 {
  font-size:.74rem;
  color:#9baac0;
  margin:.42rem 0 0 0;
  overflow-wrap:anywhere;
  line-height:1.38;
}
.fx-runtime-summary-v19220rc8 {
  display:grid;
  gap:.32rem;
  line-height:1.42;
}
.fx-runtime-summary-v19220rc8 .fx-runtime-title {font-weight:800;overflow-wrap:anywhere;}
.fx-runtime-summary-v19220rc8 .fx-runtime-line {font-size:.80rem;color:#aebbd0;overflow-wrap:anywhere;}
@media(max-width:700px) {
  .fx-status-grid-v19220rc8 {grid-template-columns:1fr;gap:.56rem;}
  .fx-status-card-v19220rc8 {padding:.72rem .76rem;border-radius:12px;}
  .fx-status-value-v19220rc8 {font-size:.98rem;}
  .fx-status-sub-v19220rc8 {font-size:.76rem;line-height:1.42;}
}
</style>
"""


def currency_status_html(cards: Sequence[tuple[object, object, object]]) -> str:
    rows = []
    for label, value, sub in cards:
        rows.append(
            '<div class="fx-status-card-v19220rc8">'
            f'<div class="fx-status-label-v19220rc8">{escape(str(label))}</div>'
            f'<div class="fx-status-value-v19220rc8">{escape(str(value))}</div>'
            f'<div class="fx-status-sub-v19220rc8">{escape(str(sub))}</div>'
            '</div>'
        )
    return currency_status_css() + '<div class="fx-status-grid-v19220rc8">' + ''.join(rows) + '</div>'


def currency_runtime_summary_html(*, title: object, quote_time: object, checked_time: object, next_time: object, error: object = "") -> str:
    error_html = f'<div class="fx-runtime-line">Feil: {escape(str(error))}</div>' if str(error or "").strip() else ""
    return (
        currency_status_css()
        + '<div class="fx-runtime-summary-v19220rc8">'
        + f'<div class="fx-runtime-title">{escape(str(title))}</div>'
        + f'<div class="fx-runtime-line">Kurssitat: {escape(str(quote_time))}</div>'
        + f'<div class="fx-runtime-line">Sist kontrollert: {escape(str(checked_time))}</div>'
        + f'<div class="fx-runtime-line">Neste kontroll: {escape(str(next_time))}</div>'
        + error_html
        + '</div>'
    )


def special_banner_enabled(settings: Mapping[str, object] | None, session_state: Mapping[str, object] | None = None) -> bool:
    """Return the immediately visible special-banner state.

    Streamlit updates widget state before restarting the script.  The widget
    state is therefore authoritative during the rerun that saves the setting;
    consulting it prevents one stale render and the large empty banner shell.
    """
    session_state = session_state or {}
    if "special_watch_enabled_v18619" in session_state:
        return bool(session_state.get("special_watch_enabled_v18619"))
    settings = settings or {}
    return bool(settings.get("special_watch_banner_enabled_v18615", True))


def data_freshness_label(value: datetime | str | None, *, now: datetime | None = None, fresh_minutes: int = 20, stale_minutes: int = 120) -> tuple[str, str]:
    if not value:
        return "Mangler tidspunkt", "missing"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00")) if not isinstance(value, datetime) else value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        age_minutes = max(0, int((current.astimezone(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() // 60))
    except Exception:
        return "Ugyldig tidspunkt", "error"
    if age_minutes <= fresh_minutes:
        return f"Ferske data ({age_minutes} min)", "fresh"
    if age_minutes <= stale_minutes:
        return f"Forsinkede data ({age_minutes} min)", "delayed"
    return f"Foreldede data ({age_minutes} min)", "stale"


REFERENCE_WIDTHS = (390, 768, 1366, 1920)
