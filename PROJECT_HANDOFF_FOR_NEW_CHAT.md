# Project handoff – v18.5.35 Control Center Consolidation + Lazy Panels

Header should show `Professional Trading Workspace v18.5.35`.

Key changes:
- AI Kontrollsenter uses lazy panel selection instead of `st.tabs`, so hidden panels do not render/start heavy work.
- Added Kontrollsenter panels: News, Interactive/Technical analysis, Market/ranking, Watchlist/signals, System/Admin.
- Removed the old standalone System/Admin and Watchlist/signals sections from the main page.
- Runtime data is excluded; only `.gitkeep` remains in runtime folders.
