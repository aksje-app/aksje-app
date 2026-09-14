# Validation report - RC16.31bw

- Python compile: PASS (`norway_exchange_universe.py`, `app_version.py`, new BW test module).
- New BW parser tests: 7/7 PASS.
- Combined BW + BU + BT + BR + compatible BV targeted tests: 31 PASS when obsolete historical version/old combined-CSV-contract assertions are excluded by design.
- Regression coverage includes: per-MIC CSV with blank market labels, all three MIC combination, conflicting-market rejection, real HTML-cell DataTables rows, mapping rows, and the exact observed 294-record Render scenario reaching `OFFICIAL_LIVE` in a controlled test.
- Full repository pytest collection was attempted but the build environment does not contain runtime dependency `yfinance==1.6.0`; six unrelated scanner/analysis modules therefore fail at collection before tests execute. This is an environment limitation, not a BW test failure.
- External Euronext live execution is unavailable from the isolated build container; Render live acceptance remains mandatory.
- Investment, BUY/risk, Fresh Trend, Paper Trade, evidence and portfolio thresholds are unchanged.
