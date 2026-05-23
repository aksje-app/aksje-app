from __future__ import annotations

import csv
import html
import io
import json
import re
import zipfile
from datetime import datetime
from typing import Any, Mapping, Sequence


SNAPSHOT_SETTINGS_KEY = "alpha_radar_saved_snapshots"
OBSERVATION_SETTINGS_KEY = "alpha_radar_observation_list"


def alpha_radar_candidate_tickers(result: Mapping[str, Any]) -> list[str]:
    seen: set[str] = set()
    tickers: list[str] = []
    for row in result.get("candidates") or []:
        if not isinstance(row, Mapping):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)
    return tickers


def alpha_radar_result_basename(result: Mapping[str, Any]) -> str:
    created = str(result.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M"))
    scope = str(result.get("scope") or result.get("market_cap_filter") or "alpha-radar")
    clean = re.sub(r"[^A-Za-z0-9]+", "_", f"{created}_{scope}").strip("_").lower()
    return clean[:90] or "alpha_radar_result"


def alpha_radar_result_to_csv(result: Mapping[str, Any]) -> bytes:
    fields = [
        "rank",
        "ticker",
        "name",
        "market",
        "horizon",
        "mode",
        "hidden_potential_score",
        "underfollowed_score",
        "inflection_score",
        "catalyst_score",
        "insider_score",
        "volume_score",
        "macro_score",
        "risk_score",
        "data_quality",
        "market_cap",
        "why_now",
        "signals",
        "reject_reasons",
        "warning_reasons",
        "manual_review",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in result.get("candidates") or []:
        if not isinstance(row, Mapping):
            continue
        out = dict(row)
        for key in ("signals", "reject_reasons", "warning_reasons"):
            value = out.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                out[key] = "; ".join(str(item) for item in value)
        writer.writerow(out)
    return buffer.getvalue().encode("utf-8-sig")


def _clean_cell(value: Any) -> str:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "; ".join(str(item) for item in value)
    if isinstance(value, Mapping):
        return json.dumps(dict(value), ensure_ascii=False, default=str)
    if value is None:
        return ""
    return str(value)


def _sheet_xml(rows: Sequence[Sequence[Any]]) -> str:
    out = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        "<sheetData>",
    ]
    for r_idx, row in enumerate(rows, start=1):
        out.append(f'<row r="{r_idx}">')
        for c_idx, value in enumerate(row, start=1):
            cell_ref = f"{chr(64 + c_idx) if c_idx <= 26 else 'A' + chr(64 + c_idx - 26)}{r_idx}"
            text = html.escape(_clean_cell(value))
            out.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        out.append("</row>")
    out.extend(["</sheetData>", "</worksheet>"])
    return "".join(out)


def alpha_radar_result_to_xlsx(result: Mapping[str, Any]) -> bytes:
    candidates = [row for row in result.get("candidates") or [] if isinstance(row, Mapping)]
    excluded = [row for row in result.get("excluded_samples") or [] if isinstance(row, Mapping)]
    context = result.get("input_context") if isinstance(result.get("input_context"), Mapping) else {}
    summary_rows = [
        ["Field", "Value"],
        ["created_at", result.get("created_at")],
        ["scope", result.get("scope")],
        ["engine", result.get("analysis_engine") or result.get("mode")],
        ["horizon", result.get("horizon")],
        ["mode", result.get("mode")],
        ["precision", result.get("precision_level")],
        ["market_cap_filter", result.get("market_cap_filter")],
        ["scanned_count", result.get("scanned_count")],
        ["scored_count", result.get("scored_count")],
        ["excluded_count", result.get("excluded_count")],
        ["disclaimer", result.get("disclaimer")],
    ]
    candidate_fields = [
        "rank", "ticker", "name", "market", "horizon", "mode", "hidden_potential_score",
        "underfollowed_score", "inflection_score", "catalyst_score", "insider_score",
        "volume_score", "macro_score", "evidence_score", "risk_score", "market_cap",
        "data_quality", "why_now", "signals", "reject_reasons", "warning_reasons", "manual_review",
    ]
    candidate_rows = [candidate_fields] + [[row.get(field) for field in candidate_fields] for row in candidates]
    signal_rows = [["ticker", "factor", "score", "quality"]]
    quality_rows = [["ticker", "factor", "quality"]]
    for row in candidates:
        scores = row.get("factor_scores") if isinstance(row.get("factor_scores"), Mapping) else {}
        qualities = row.get("factor_quality") if isinstance(row.get("factor_quality"), Mapping) else {}
        for factor, score in scores.items():
            signal_rows.append([row.get("ticker"), factor, score, qualities.get(factor)])
        for factor, quality in qualities.items():
            quality_rows.append([row.get("ticker"), factor, quality])
    excluded_rows = [["ticker", "reasons", "market_cap"]] + [[row.get("ticker"), row.get("reasons"), row.get("market_cap")] for row in excluded]
    raw_rows = [["Key", "Value"]] + [[key, value] for key, value in context.items()]

    sheets = [
        ("Summary", summary_rows),
        ("Candidates", candidate_rows),
        ("Signals", signal_rows),
        ("Data quality", quality_rows),
        ("Excluded", excluded_rows),
        ("Raw input", raw_rows),
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
""" + "".join(f'<Override PartName="/xl/worksheets/sheet{idx}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for idx, _sheet in enumerate(sheets, start=1)) + "</Types>")
        zf.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""")
        zf.writestr("xl/workbook.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>""" + "".join(
            f'<sheet name="{html.escape(name[:31])}" sheetId="{idx}" r:id="rId{idx}"/>' for idx, (name, _rows) in enumerate(sheets, start=1)
        ) + "</sheets></workbook>")
        zf.writestr("xl/_rels/workbook.xml.rels", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">""" + "".join(
            f'<Relationship Id="rId{idx}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{idx}.xml"/>' for idx, _sheet in enumerate(sheets, start=1)
        ) + "</Relationships>")
        for idx, (_name, rows) in enumerate(sheets, start=1):
            zf.writestr(f"xl/worksheets/sheet{idx}.xml", _sheet_xml(rows))
    return buffer.getvalue()


def alpha_radar_result_to_json(result: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(result), ensure_ascii=False, indent=2, default=str).encode("utf-8")


def alpha_radar_result_to_ticker_text(result: Mapping[str, Any]) -> bytes:
    return "\n".join(alpha_radar_candidate_tickers(result)).encode("utf-8")


def alpha_radar_result_to_print_html(result: Mapping[str, Any]) -> bytes:
    title = "Alpha Radar result"
    created = html.escape(str(result.get("created_at") or ""))
    scope = html.escape(str(result.get("scope") or ""))
    mode = html.escape(str(result.get("mode") or ""))
    horizon = html.escape(str(result.get("horizon") or ""))
    precision = html.escape(str(result.get("precision_level") or ""))
    market_filter = html.escape(str(result.get("market_cap_filter") or ""))
    scanned = html.escape(str(result.get("scanned_count") or 0))
    scored = html.escape(str(result.get("scored_count") or 0))
    excluded = html.escape(str(result.get("excluded_count") or 0))
    rows: list[str] = []
    for row in result.get("candidates") or []:
        if not isinstance(row, Mapping):
            continue
        signals = row.get("signals") if isinstance(row.get("signals"), list) else []
        warnings = row.get("warning_reasons") if isinstance(row.get("warning_reasons"), list) else []
        rejects = row.get("reject_reasons") if isinstance(row.get("reject_reasons"), list) else []
        qualities = row.get("factor_quality") if isinstance(row.get("factor_quality"), Mapping) else {}
        metric_rows = [
            ("Oversett/forventning", row.get("underfollowed_score"), qualities.get("underfollowed") or qualities.get("expectation_change")),
            ("Vendepunkt/earnings", row.get("inflection_score"), qualities.get("inflection") or qualities.get("earnings_surprise")),
            ("Katalysator", row.get("catalyst_score"), qualities.get("catalyst") or qualities.get("catalyst_altdata_macro")),
            ("Insider/eierskap", row.get("insider_score"), qualities.get("insider_bjellesau") or qualities.get("ownership_insider")),
            ("Volum/bekreftelse", row.get("volume_score"), qualities.get("volume_accumulation") or qualities.get("market_confirmation")),
            ("Makro/fundamental", row.get("macro_score"), qualities.get("macro_second_order") or qualities.get("fundamental_acceleration")),
            ("Risiko", row.get("risk_score"), "beregnet"),
            ("Borsverdi", row.get("market_cap"), ""),
        ]
        metric_html = "".join(
            f"<tr><td>{html.escape(label)}</td><td>{html.escape(_clean_cell(value) or 'N/A')}</td><td>{html.escape(str(quality or ''))}</td></tr>"
            for label, value, quality in metric_rows
        )
        rows.append(
            "<section class='candidate'>"
            f"<h2>#{html.escape(str(row.get('rank') or '-'))} {html.escape(str(row.get('ticker') or '-'))}"
            f"<span>{html.escape(str(row.get('hidden_potential_score') or row.get('alpha_score') or '-'))}</span></h2>"
            f"<p class='meta'>{html.escape(str(row.get('name') or ''))} | {html.escape(str(row.get('market') or ''))} | {html.escape(str(row.get('horizon') or ''))} | {html.escape(str(row.get('mode') or ''))} | data: {html.escape(str(row.get('data_quality') or 'OK'))}</p>"
            f"<table><thead><tr><th>Faktor</th><th>Verdi</th><th>Datakvalitet</th></tr></thead><tbody>{metric_html}</tbody></table>"
            f"<p>{html.escape(str(row.get('why_now') or row.get('thesis') or ''))}</p>"
            f"<p><b>Signaler:</b> {html.escape(', '.join(str(x) for x in signals) or '-')}</p>"
            f"<p><b>Sjekk/avslag:</b> {html.escape('; '.join(str(x) for x in rejects) or 'ingen harde avslag')}</p>"
            f"<p><b>Datavarsel:</b> {html.escape('; '.join(str(x) for x in warnings) or 'ingen')}</p>"
            f"<p class='review'>{html.escape(str(row.get('manual_review') or ''))}</p>"
            "</section>"
        )
    body = "\n".join(rows) or "<p>Ingen kandidater i resultatet.</p>"
    document = f"""<!doctype html>
<html lang="no">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 28px; color: #111827; }}
    h1 {{ margin-bottom: 4px; }}
    .meta {{ color: #4b5563; font-size: 13px; }}
    .candidate {{ border-top: 1px solid #d1d5db; padding: 14px 0; page-break-inside: avoid; }}
    .candidate h2 {{ display: flex; justify-content: space-between; font-size: 18px; margin: 0 0 6px 0; }}
    .candidate h2 span {{ color: #047857; }}
    table {{ border-collapse: collapse; width: 100%; margin: 8px 0 10px 0; }}
    th, td {{ border: 1px solid #d1d5db; padding: 5px 7px; text-align: left; font-size: 12px; }}
    th {{ background: #f3f4f6; }}
    .review {{ color: #92400e; }}
    @media print {{ button {{ display: none; }} body {{ margin: 16mm; }} }}
  </style>
</head>
<body>
  <button onclick="window.print()">Skriv ut / lagre som PDF</button>
  <h1>Alpha Radar</h1>
  <p class="meta">{created} | {scope} | {mode} | {horizon} | {precision} | {market_filter}</p>
  <p class="meta">Scannet {scanned} | scoret {scored} | ekskludert {excluded}</p>
  <p>Hypoteseliste for manuell analyse. Ikke investeringsraad og ikke automatisk handel.</p>
  {body}
</body>
</html>"""
    return document.encode("utf-8")


def save_alpha_radar_snapshot(result: Mapping[str, Any], *, max_snapshots: int = 20) -> int:
    from settings_store import load_settings, save_settings

    settings = load_settings() or {}
    snapshots = settings.get(SNAPSHOT_SETTINGS_KEY)
    if not isinstance(snapshots, list):
        snapshots = []
    payload = {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "created_at": result.get("created_at"),
        "scope": result.get("scope"),
        "horizon": result.get("horizon"),
        "mode": result.get("mode"),
        "precision_level": result.get("precision_level"),
        "market_cap_filter": result.get("market_cap_filter"),
        "limit": result.get("limit"),
        "scanned_count": result.get("scanned_count"),
        "tickers": alpha_radar_candidate_tickers(result),
        "candidates": list(result.get("candidates") or []),
        "input_fingerprint": result.get("input_fingerprint"),
        "input_context": result.get("input_context"),
    }
    snapshots = [payload] + snapshots
    settings[SNAPSHOT_SETTINGS_KEY] = snapshots[:max_snapshots]
    save_settings(settings)
    return len(payload["tickers"])


def save_alpha_radar_observation_list(result: Mapping[str, Any]) -> int:
    from settings_store import load_settings, save_settings

    settings = load_settings() or {}
    tickers = alpha_radar_candidate_tickers(result)
    settings[OBSERVATION_SETTINGS_KEY] = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "Alpha Radar",
        "tickers": tickers,
        "input_fingerprint": result.get("input_fingerprint"),
    }
    save_settings(settings)
    return len(tickers)


def alpha_radar_result_to_active_universe_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    tickers = alpha_radar_candidate_tickers(result)
    rows = []
    for row in result.get("candidates") or []:
        if not isinstance(row, Mapping):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        rows.append({
            "ticker": ticker,
            "name": row.get("name"),
            "market": row.get("market"),
            "score": row.get("hidden_potential_score") or row.get("alpha_score"),
            "status": "Alpha Radar hypotese",
            "reason": row.get("why_now") or row.get("thesis"),
            "source": "Alpha Radar",
        })
    return {
        "source": "Alpha Radar",
        "picker_reason": "Alpha Radar resultat sendt manuelt til aktivt analyseunivers.",
        "tickers": tickers,
        "rows": rows,
        "config": dict(result.get("input_context") or {}),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "matched_candidates": len(tickers),
    }


__all__ = [
    "alpha_radar_candidate_tickers",
    "alpha_radar_result_basename",
    "alpha_radar_result_to_active_universe_payload",
    "alpha_radar_result_to_csv",
    "alpha_radar_result_to_json",
    "alpha_radar_result_to_print_html",
    "alpha_radar_result_to_ticker_text",
    "alpha_radar_result_to_xlsx",
    "save_alpha_radar_observation_list",
    "save_alpha_radar_snapshot",
]
