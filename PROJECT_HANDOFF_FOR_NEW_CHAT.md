# Project handoff – v18.5.31 Header Navigation + Global Busy Indicator

## Completed
- Active main-panel selector moved to the header area above the ticker/banner strip.
- Sticky topbar now includes a global busy chip with spinner/ready state.
- Smart AI, strategy-test and strategy-test Pro update the shared busy status while running.
- NewsAPI calls are guarded: manual button calls can fetch live data; automatic scoring/event-risk calls use cache unless NEWSAPI_ALLOW_AUTO_CALLS=true.
- Forecast event-risk has its own “Bruk nyheter i hendelsesrisiko” toggle, off by default.
- Legacy cleanup from v18.5.30 remains intact.

## Smoke test
Header should show `Professional Trading Workspace v18.5.31`.

## Deploy
Upload to GitHub main, then Render → Manual Deploy → Clear build cache & deploy.
