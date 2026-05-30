import py_compile
import zipfile
from io import BytesIO
from xml.sax.saxutils import escape

from actor_registry import actor_roles, normalize_actor_row
from data_source_diagnostics import build_data_source_status
from finansavisen_bjellesau import (
    actor_rows_from_finansavisen_transactions,
    aggregate_finansavisen_by_stock,
    apply_finansavisen_bjellesau_overlay,
    build_finansavisen_overlay_snapshot,
    build_finansavisen_priority_views,
    build_finansavisen_report,
    build_finansavisen_report_html,
    build_finansavisen_report_pdf,
    build_finansavisen_stock_detail_views,
    decision_rows_from_finansavisen,
    finansavisen_stock_detail_options,
    infer_period_from_filename,
    merge_finansavisen_transactions,
    parse_finansavisen_transaction_xlsx,
    sort_periods,
)
from source_budget import estimate_source_budget, source_budget_rows


def _xlsx_bytes(rows):
    shared = []
    shared_index = {}

    def s(value):
        text = "" if value is None else str(value)
        if text not in shared_index:
            shared_index[text] = len(shared)
            shared.append(text)
        return shared_index[text]

    sheet_rows = []
    for r_idx, row in enumerate(rows, start=1):
        cells = []
        for c_idx, value in enumerate(row):
            col = chr(ord("A") + c_idx)
            cells.append(f'<c r="{col}{r_idx}" t="s"><v>{s(value)}</v></c>')
        sheet_rows.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
    shared_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{len(shared)}" uniqueCount="{len(shared)}">'
        + "".join(f"<si><t>{escape(text)}</t></si>" for text in shared)
        + "</sst>"
    )
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        + "".join(sheet_rows)
        + "</sheetData></worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Transactions" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/sharedStrings.xml", shared_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buffer.getvalue()


def _sample_xlsx():
    return _xlsx_bytes(
        [
            [
                "Investor",
                "Aksje",
                "Endring i aksjer",
                "Rel.endring",
                "Transaksjonverdi",
                "Ny eierandel",
                "Ny beholding",
                "UtfÃƒÂ¸rt av",
                "Estimert dato",
            ],
            ["Helge GÃƒÂ¥sÃƒÂ¸", "NORBIT", "105000", "100%", "19,82 M", "0,16419%", "105000", "FROY KAPITAL AS", "20.05.2026"],
            ["Egil Stenshagen", "AF Gruppen", "85000", "11,49%", "15,53 M", "0,72576%", "824977", "STENSHAGEN INVEST", "20.05.2026"],
            ["Sverre Bjerkeli", "LINK", "-468094", "-6,79%", "-13,00 M", "2,09959%", "6422680", "HVALER INVEST AS", "20.05.2026"],
        ]
    )


def test_finansavisen_period_inference_uses_filename_tokens():
    assert infer_period_from_filename("transaction 1D.xlsx") == "1D"
    assert infer_period_from_filename("transaction 1M.xlsx") == "1M"
    assert infer_period_from_filename("transaction 3M.xlsx") == "3M"
    assert infer_period_from_filename("transaction 6M.xlsx") == "6M"
    assert infer_period_from_filename("transaction ALLE.xlsx") == "ALLE"
    assert sort_periods(["ALLE", "1M", "6M", "1D"]) == ["1D", "1M", "6M", "ALLE"]


def test_finansavisen_xlsx_parser_dedupes_periods_and_matches_tickers():
    rows_1d = parse_finansavisen_transaction_xlsx(_sample_xlsx(), "transaction_1d.xlsx", source_period="1D")
    rows_6m = parse_finansavisen_transaction_xlsx(_sample_xlsx(), "transaction_6m.xlsx", source_period="6M")
    merged = merge_finansavisen_transactions(rows_1d, rows_6m)
    reverse_merged = merge_finansavisen_transactions(rows_6m, rows_1d)

    assert len(rows_1d) == 3
    assert len(merged) == 3
    norbit = next(row for row in merged if row["investor"] == "Helge GÃƒÂ¥sÃƒÂ¸")
    assert norbit["matched_ticker"] == "NORBT.OL"
    assert set(norbit["source_periods"]) == {"1D", "6M"}
    assert norbit["transaction_value_nok"] == 19_820_000
    reverse_norbit = next(row for row in reverse_merged if row["matched_ticker"] == "NORBT.OL")
    assert set(reverse_norbit["source_periods"]) == {"1D", "6M"}
    assert reverse_norbit["source_period"] == "1D"


def test_finansavisen_aggregates_overlay_and_report_feed_radar_evidence():
    rows = parse_finansavisen_transaction_xlsx(_sample_xlsx(), "transaction_1d.xlsx", source_period="1D")
    aggregates = aggregate_finansavisen_by_stock(rows)
    snapshot = build_finansavisen_overlay_snapshot(rows)
    enriched = apply_finansavisen_bjellesau_overlay({"ticker": "NORBT.OL", "name": "NORBIT"}, snapshot=snapshot)
    views = build_finansavisen_priority_views(rows)
    detail_options = finansavisen_stock_detail_options(rows)
    detail_views = build_finansavisen_stock_detail_views(rows, detail_options[0]["key"])
    report = build_finansavisen_report(rows)
    html_report = build_finansavisen_report_html(rows)
    pdf_report = build_finansavisen_report_pdf(rows)
    decision_rows = decision_rows_from_finansavisen(rows, ["NORBT.OL"])

    assert aggregates[0]["score"] >= 50
    assert enriched["finansavisen_bjellesau_evidence"]
    assert enriched["bjellesau_evidence"][0]["source"] == "Finansavisen Bjellesauer"
    assert enriched["bjellesau_score"] > 0
    assert views["Storste kjop"][0]["Investor"] == "Helge GÃƒÂ¥sÃƒÂ¸"
    assert "Scoreforklaring" in views["Score per aksje"][0]
    assert "Flere bjellesauer samme aksje" in views
    assert detail_views["Gruppert per dato"][0]["Dato"] == "2026-05-20"
    assert detail_views["Samlet per person"][0]["Investor"]
    assert "Endring aksjer" in detail_views["Transaksjoner"][0]
    assert "Finansavisen Bjellesauer" in report
    assert "Detalj per aksje" in report
    assert b"Skriv ut / lagre som PDF" in html_report
    assert b"Detalj per aksje" in html_report
    assert pdf_report.startswith(b"%PDF-1.4")
    assert decision_rows[0]["decision_source"] == "Finansavisen Bjellesauer"


def test_finansavisen_actor_sync_preserves_multiple_roles():
    rows = parse_finansavisen_transaction_xlsx(_sample_xlsx(), "transaction_1d.xlsx", source_period="1D")
    existing = [
        normalize_actor_row(
            {
                "active": True,
                "name": "Helge GÃƒÂ¥sÃƒÂ¸",
                "aliases": "Helge GÃƒÂ¥sÃƒÂ¸",
                "market": "Norge",
                "actor_roles": "Insider watch",
            }
        )
    ]

    merged = actor_rows_from_finansavisen_transactions(rows, existing_rows=existing)
    helge = next(row for row in merged if row["name"] == "Helge GÃƒÂ¥sÃƒÂ¸")

    assert {"Bjellesau", "Insider watch"} <= set(actor_roles(helge))
    assert "NORBT.OL" in helge["relevant_tickers"]
    assert "Helge" in helge["aliases"]


def test_finansavisen_budget_status_and_light_ui_compile():
    budget = estimate_source_budget(planned_tickers=25, source_values={"insider": True})
    rows = source_budget_rows(budget)
    status = build_data_source_status("3m")

    assert budget["finansavisen_overlay_checks"] == 25
    assert any(row["Kilde"] == "Finansavisen Bjellesauer" for row in rows)
    assert any(row["Kilde"] == "Finansavisen Bjellesauer" for row in status)

    for module in ["finansavisen_bjellesau.py", "finansavisen_bjellesau_ui.py", "alpha_radar_enrichment.py"]:
        py_compile.compile(module, doraise=True)

    source = open("finansavisen_bjellesau_ui.py", encoding="utf-8").read()
    assert "st.data_editor" not in source
    assert "Importer valgte filer" in source
    assert "finansavisen_bjellesau_period_{idx}_v1863bk" not in source
    assert "_file_period_key(upload, idx)" in source
    assert "Last ned PDF" in source
    assert "Send valgte tickere til AI Kandidattest" in source
    assert "Send hele kildegrunnlaget til AI Kandidattest" in source
    assert "Send til Beslutningsgrunnlag" in source
    assert "finansavisen_bjellesau_decision_tickers_v1864i" in source
    assert "max_selections=len(decision_options)" in source
    assert "max_selections=min(20" not in source
    assert "max_selections=min(60" not in source

    layout = open("workspace_layout.py", encoding="utf-8").read()
    assert '"finansavisen", "bjellesau"' in layout
    assert 'ai_candidate_group_name = "AI Kandidattest"' in layout


def test_finansavisen_test2_candidate_rows_use_selected_tickers():
    from finansavisen_bjellesau_ui import _finansavisen_candidate_rows_for_tickers

    rows = parse_finansavisen_transaction_xlsx(_sample_xlsx(), "transaction_1d.xlsx", source_period="1D")
    candidates = _finansavisen_candidate_rows_for_tickers(rows, ["NORBT.OL", "MISSING.OL"])

    assert len(candidates) == 1
    assert candidates[0]["ticker"] == "NORBT.OL"
    assert candidates[0]["source"] == "Finansavisen Bjellesauer"
    assert "AI Kandidattest" in candidates[0]["recommended_action"]



