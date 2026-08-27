"""Hard export gate for report packages.

The public package must contain PDF, TXT and JSON built from one canonical run.
The gate rejects version/identity/ranking/decision drift before a ZIP is exposed.
"""
from __future__ import annotations
import io, json, re, zipfile
from copy import deepcopy
from typing import Any, Mapping
from app_version import APP_VERSION

LEGACY_PUBLIC_RANKING_KEYS = {
    "priority_top3", "raw_top3", "diverse_top3", "final_decision_top3",
    "evidence_ready_top3", "report_top3", "top3", "top_10", "ranking_explanation",
}

def _normalise_learning_action(value: Any) -> str:
    return str(value or "").strip().upper()

def _normalise_learning_quantity(value: Any) -> float:
    return round(float(str(value or 0).replace(",", ".")), 8)

def _normalise_learning_price(value: Any) -> float:
    # TXT and PDF deliberately display monetary fills with two decimals.  The
    # audit must compare the same public representation, not hidden JSON
    # precision that those channels cannot reproduce.
    return round(float(str(value or 0).replace(",", ".")), 2)

def canonical_public_run(run: Mapping[str, Any]) -> dict[str, Any]:
    from report_integrity import canonical_report_view
    from report_contracts import ensure_report_document
    from report_channel_consistency import attach_channel_projection
    result = canonical_report_view(deepcopy(dict(run or {})))
    result["version"] = APP_VERSION
    result["app_version"] = APP_VERSION
    # Remove competing public ranking structures from the exported copy only.
    for key in LEGACY_PUBLIC_RANKING_KEYS:
        result.pop(key, None)
    result.pop("decision_report", None)
    result.pop("report_document", None)
    result.pop("report_contract_validation", None)
    document = ensure_report_document(result)
    projection = attach_channel_projection(result, document)
    result["public_report_contract"] = deepcopy(projection)
    result["channel_consistency"] = deepcopy(projection)
    return result

def expected_contract(run: Mapping[str, Any]) -> dict[str, Any]:
    projection = dict(run.get("public_report_contract") or run.get("channel_consistency") or {})
    learning = run.get("learning_portfolio_summary") if isinstance(run.get("learning_portfolio_summary"), Mapping) else {}
    learning_fills = []
    for row in learning.get("learning_fills") or []:
        if not isinstance(row, Mapping):
            continue
        learning_fills.append({
            "ticker": str(row.get("ticker") or "").upper(),
            "action": _normalise_learning_action(row.get("side") or row.get("action")),
            "quantity": _normalise_learning_quantity(row.get("quantity")),
            "price": _normalise_learning_price(row.get("price", row.get("fill_price"))),
        })
    return {
        "report_id": str(projection.get("report_id") or run.get("report_id") or run.get("run_id") or ""),
        "app_version": str(run.get("app_version") or run.get("version") or ""),
        "ranking": list(projection.get("ranking") or []),
        "decision_count": int(projection.get("decision_count") or 0),
        "learning_fills": learning_fills,
    }

def _text_contract(text: str) -> dict[str, Any]:
    rid = re.search(r"Rapport-ID:\s*([^\n\r]+)", text, re.I)
    ver = re.search(r"Appversjon:\s*([^\n\r]+)", text, re.I)
    ranking=[]
    # Canonical TXT rows use '#<rank> TICKER ... Beslutning: <label>'.
    for m in re.finditer(r"^#(\d+)\s+([A-Z0-9.\-]+).*?Beslutning:\s*([^\n\r]+)$", text, re.I|re.M):
        ranking.append({"rank":int(m.group(1)),"ticker":m.group(2).upper(),"decision_label":m.group(3).strip()})
    learning=[]
    for m in re.finditer(r"^-\s+([A-Z0-9.\-]+)\s+·\s+(BUY|SELL)\s+·\s+antall\s+([0-9.,]+)\s+·\s+pris\s+([0-9.,]+)", text, re.I|re.M):
        learning.append({
            "ticker": m.group(1).upper(),
            "action": _normalise_learning_action(m.group(2)),
            "quantity": _normalise_learning_quantity(m.group(3)),
            "price": _normalise_learning_price(m.group(4)),
        })
    return {"report_id": rid.group(1).strip() if rid else "", "app_version": ver.group(1).strip() if ver else "", "ranking": ranking, "learning_fills": learning}

def validate_artifacts(*, run: Mapping[str, Any], pdf: bytes, txt: bytes, json_bytes: bytes) -> dict[str, Any]:
    errors=[]
    if not pdf or not bytes(pdf).startswith(b"%PDF-"): errors.append("PDF mangler eller er ugyldig")
    if not txt: errors.append("TXT mangler")
    if not json_bytes: errors.append("JSON mangler")
    if errors: return {"ok":False,"errors":errors}
    expected=expected_contract(run)
    try: payload=json.loads(json_bytes.decode("utf-8"))
    except Exception as exc: return {"ok":False,"errors":[f"JSON kan ikke leses: {exc}"]}
    actual=expected_contract(payload)
    for key in ("report_id","app_version","ranking","decision_count","learning_fills"):
        if actual.get(key)!=expected.get(key): errors.append(f"JSON {key} avviker fra canonical kontrakt")
    text=txt.decode("utf-8",errors="replace")
    tc=_text_contract(text)
    if tc["report_id"]!=expected["report_id"]: errors.append("TXT rapport-ID avviker")
    if tc["app_version"]!=expected["app_version"]: errors.append("TXT versjon avviker")
    expected_text_ranking = [{
        "rank": int(row.get("rank") or index),
        "ticker": str(row.get("ticker") or "").upper(),
        "decision_label": str(row.get("decision_label") or row.get("decision") or "").strip(),
    } for index, row in enumerate(expected["ranking"], 1)]
    if tc["ranking"] != expected_text_ranking:
        errors.append("TXT kjøpsrangering eller beslutninger avviker")
    if tc["learning_fills"] != expected["learning_fills"]:
        errors.append("TXT læringshandler avviker fra canonical fills")
    # PDF text verification when pypdf is available.
    try:
        from pypdf import PdfReader
        pdf_text="\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
        if expected["report_id"] and expected["report_id"] not in pdf_text: errors.append("PDF rapport-ID avviker eller mangler")
        if expected["app_version"] and expected["app_version"] not in pdf_text: errors.append("PDF versjon avviker eller mangler")
        for row in expected["ranking"]:
            if str(row.get("ticker") or "") not in pdf_text: errors.append(f"PDF mangler rangert ticker {row.get('ticker')}")
            decision_label = str(row.get("decision_label") or row.get("decision") or "").strip()
            if decision_label and decision_label not in pdf_text:
                errors.append(f"PDF mangler beslutning for {row.get('ticker')}")
        for row in expected["learning_fills"]:
            if row["ticker"] not in pdf_text:
                errors.append(f"PDF mangler læringshandler for {row['ticker']}")
            price_no = f"{row['price']:.2f}".replace(".", ",")
            if price_no not in pdf_text:
                errors.append(f"PDF mangler læringspris for {row['ticker']}")
        fonts=set()
        for page in PdfReader(io.BytesIO(pdf)).pages:
            resources=page.get("/Resources") or {}
            for ref in (resources.get("/Font") or {}).values():
                fonts.add(str(ref.get_object().get("/BaseFont") or ""))
        if not any("NotoSans" in name for name in fonts):
            errors.append("PDF har ikke innebygd Noto Sans")
        if not list(PdfReader(io.BytesIO(pdf)).outline or []):
            errors.append("PDF mangler bokmerker")
    except Exception as exc:
        errors.append(f"PDF-konsistenskontroll kunne ikke kjøres: {exc}")
    return {"ok":not errors,"errors":errors,"expected":expected}

def validate_zip(payload: bytes) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            bad=z.testzip(); names=set(z.namelist())
            required={"report/report.pdf","report/report.txt","report/report.json","report/candidate_scores.json","REPORT_CONSISTENCY_AUDIT.json"}
            errors=[]
            if bad: errors.append(f"Korrupt ZIP-medlem: {bad}")
            missing=sorted(required-names)
            if missing: errors.append("Mangler: "+", ".join(missing))
            return {"ok":not errors,"errors":errors,"files":sorted(names)}
    except Exception as exc:
        return {"ok":False,"errors":[str(exc)]}
