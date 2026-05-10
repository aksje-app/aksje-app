# Project handoff – v18.5.22 Strict Universe Mode + Progress UI

Focus for this release:

- Smart Universe Picker modes are now strict source-of-truth for Smart AI scans.
- `Enkeltaksje` scans only the selected manual ticker, with no market fallback.
- `Manuell liste`, `Top Picks`, `Watchlist`, `Paper trading`, and `Portefølje` scan only their own selected source.
- `Markedvalg` and `Multi-marked` use market scopes only and do not silently prepend stale manual tickers.
- Remaining Analyseunivers result/status panels use inline dark compact rows to avoid large white empty Streamlit/native panels.
- Added visible progress/spinner UI for:
  - Smart AI-utvalg
  - Strategi-test
  - Strategi-test Pro / optimalisering
- Version source updated to `v18.5.22` via `app_version.py`.

Validation:

- `python -m compileall .`
- `pytest -q` → 18 passed

Recommended deploy:

1. Upload all files to GitHub `main`.
2. Render → Manual Deploy → Clear build cache & deploy.
3. Confirm topbar says `Professional Trading Workspace v18.5.22`.
4. Test `Workspace-modus = Enkeltaksje`, ticker `AAPL`, then run Smart AI-utvalg. Result should scan and show only AAPL.
5. Confirm no large white blank panels appear in Analyseunivers.
