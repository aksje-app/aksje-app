# RC16.31bm - Early Trend and Breakout Intelligence

## Purpose
RC16.31bm adds a separate descriptive early-signal layer for Norway production stabilization. It is designed to surface technically strengthening stocks earlier and to explain clearly which signals are present, why they can support further upside, and what would invalidate the setup.

## Changes
- Adds 5d/10d/20d momentum acceleration metrics.
- Adds price/SMA20, SMA20/SMA50 and SMA50/SMA200 structure.
- Detects active/recent golden-cross structure.
- Adds 20d and 60d breakout detection against the previous high.
- Adds RSI 50/70 crossing context and overbought cautions.
- Adds On Balance Volume pressure over 5/10/20 sessions and volume confirmation versus 20d average.
- Adds support/resistance references from previous 20d/60d highs, SMA20/SMA50 and recent lows.
- Adds cross-sectional 20d/60d relative-strength percentiles for the active market and 20d percentile within sector.
- Adds `early_signal_watchlist` across all analysed candidates, independent of overall investment-score rank.
- Adds deterministic Norwegian explanations: continuation case, confirmation checks, failure checks and cautions.
- UI trend detail now shows breakout reference levels, RSI 30/50/70, volume panel and the full early-signal explanation.
- Technical PDF adds an Early Trend / Breakout section with top signals.

## Safety and policy
The new layer is descriptive only. It does not change production buy thresholds, risk limits, liquidity gates, portfolio rules, Autonomy authority or trade authorisation. An early signal can move a stock onto the observation watchlist, but cannot by itself create a buy or order.

## Production scope
`PRODUCTION_NORWAY_ONLY=true` remains the default production-stabilisation mode. Sweden and USA remain in the architecture but are not re-enabled by this release.
