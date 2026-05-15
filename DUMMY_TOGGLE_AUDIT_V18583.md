# Dummy-toggle audit v18.5.83

Scope for this pass: critical stability controls in Paper Trading / Auto Trading.

## ACTIVE

- `auto_trading_enabled`: stored in app settings and used to enable/disable auto flow.
- `auto_trading_safe_edit_mode`: stored in app settings; pauses auto trading while editing.
- `pushover_enabled`: stored in app settings and checked before sending notifications.
- `notify_paper_trades`, `notify_watchlist_signal_changes`, `notify_high_confidence_only`, `notify_min_confidence`: stored and used by notification/watchlist flow.

## FIXED / CONNECTED IN THIS PASS

- `auto_buy_safety_mode`: was visible in UI and stored, but was not part of default settings and was not enforced in `paper_buy()`.
  - Added to `DEFAULT_SETTINGS`.
  - Enforced in `trading_engine.paper_buy()` for new BUY operations.
  - Blocks new BUY when portfolio data is invalid or cash is unavailable.
  - Does not block SELL/exit paths.

## CLARIFIED IN UI

- Paper Trading start capital vs. portfolio value:
  - Start capital is now described as reset baseline.
  - Portfolio value is described as cash + open positions.
  - Buying power is shown as cash only.
  - Unrealized P/L is shown separately and does not increase buying power before sell.

## NOT CHANGED IN THIS PASS

- Global update responsive layout.
- Toast/status overlap.
- Pushover API test details beyond existing Send testvarsel button.

These are suitable for the next UI/UX GO batch.
