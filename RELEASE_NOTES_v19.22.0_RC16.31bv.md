# RC16.31bv - Official Euronext CSV Universe Closure

Purpose: close the Norway-universe source failure observed in BR-BU and obtain the complete official Oslo equity universe without parsing the JavaScript-rendered product table.

Changes:
- Primary source is now Euronext Live's current product-directory CSV export: `/en/pd_es/data/stocks/download`.
- First request is scoped directly to `XOSL,MERK,XOAS`; if that export is unavailable or incomplete, a second official all-stocks CSV export is requested and strictly filtered back to those three MICs/markets.
- CSV parsing is locale tolerant: English/Norwegian column names, BOM, metadata preamble, semicolon/tab/comma separators, quoted fields and optional MIC column.
- Unknown markets are no longer silently coerced to Oslo Børs. A row must resolve to XOSL, MERK or XOAS before it enters the Norway master.
- Added a current `/en/pd_es/data/stocks` DataTables JSON fallback using the present product-directory contract (`dp_stocks`, `df_stocks2`, `dt_stocks_osl`) before the old legacy endpoint.
- Existing HTML parser, legacy endpoint, durable last-known-good master, `FALLBACK_UNVERIFIED` protection and BU source diagnostics remain as defensive fallbacks.
- Successful source is reported as `Euronext official CSV export` and final status remains `OFFICIAL_LIVE` only when the validated universe has at least 150 rows.
- No scoring, BUY threshold, risk, Fresh Trend, Paper Trade, evidence-budget, portfolio or market-policy changes.
