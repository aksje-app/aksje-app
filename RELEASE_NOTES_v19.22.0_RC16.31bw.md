# RC16.31bw - Euronext Real Payload Parser Closure

Purpose: close the exact live Render failure observed in BV, where Euronext returned 294 Oslo records but the application parsed 0.

Changes:
- The official CSV export is now fetched separately for each Norway MIC: `XOSL`, `MERK`, and `XOAS`.
- Per-MIC CSV parsing treats the server-side MIC filter as authoritative when the display `Market` field is blank or non-standard, while rejecting rows whose explicit market conflicts with the requested MIC.
- The current `/en/pd_es/data/stocks` DataTables JSON parser now accepts Euronext's real HTML-cell payloads, not only plain string arrays.
- JSON parsing can recover Name, ISIN, Symbol and MIC/Market from HTML cell text, `data-*` attributes and embedded MICs/URLs.
- Mapping/dict DataTables rows are also accepted defensively.
- Current JSON diagnostics now include raw row count/type and identify the flexible HTML-cell parser.
- The official universe still requires at least 150 validated instruments before `OFFICIAL_LIVE` can be emitted.
- Existing durable last-known-good handling, BU diagnostics, fallback protection and Norway-only policy remain unchanged.
- No scoring, BUY threshold, risk, Fresh Trend, Paper Trade, evidence-budget, portfolio or market-policy changes.
