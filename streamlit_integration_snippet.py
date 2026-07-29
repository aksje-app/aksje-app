"""
Integration snippet for v18.6.1.
Paste near top of main Streamlit app.
"""

from VERSION import APP_VERSION, APP_BUILD_LABEL
from desktop_ux_patch import inject_desktop_ux_css, render_compact_control_bar, render_compact_status
from daily_report_v18_6_1 import render_ai_market_briefing

inject_desktop_ux_css()

# Optional: show version in sidebar/header
# st.caption(APP_BUILD_LABEL)

# Replace old large control/global-update section with:
# render_compact_control_bar(global_update_callback=run_global_update)
# render_compact_status(status=current_status, last_update=last_global_update_text)

# Replace old Daily Report cache dump with:
# render_ai_market_briefing(
#     ranking_df=ranking_df,
#     forecast_fn=make_forecast_for_ticker,
#     watchlist=watchlist_tickers,
#     positions_df=positions_df,
# )
