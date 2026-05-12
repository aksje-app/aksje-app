# Project handoff – v18.5.38 Fund / ETF Analyzer v1 + Progress

Header should show `Professional Trading Workspace v18.5.38`.

Key update: Kontrollsenter has a new lazy `🏦 Fond / ETF-analyse` panel. It analyses funds and ETFs only when the user presses the run button. It supports Indeksfond / Aktivt fond / ETF / Alle, manual fund/ETF ticker lists, Rask/Normal/Grundig test modes, benchmark comparison, cost/risk/return/max drawdown metrics, a fund-specific Decision Quality score and visible per-fund/per-test progress.

The fund module is intentionally separate from stock scoring: index funds/ETFs are treated as potential low-cost foundation holdings, while active funds must show enough benchmark/value evidence to justify costs.

Runtime data stays out of GitHub; keep only `.gitkeep` in `data/`, `data/forecasts/` and `data/services/`.

Current focus: v18.5.38 Fund / ETF Analyzer v1 + Progress.
