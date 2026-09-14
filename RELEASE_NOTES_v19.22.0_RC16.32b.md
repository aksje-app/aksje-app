# v19.22.0 RC16.32b – Super Portfolio Intelligence

RC16.32b extends the isolated Super Portfolio Shadow module introduced in RC16.32a. It does not alter the authoritative Autonomy order chain and does not submit real orders.

## Added
- Soft sector concentration penalty; no hard sector quota.
- Soft correlation penalty when candidate correlation metadata is available.
- Adjusted portfolio score used for dynamic target weights.
- Ranking Velocity with rank history and directional arrows (↑ / ↓ / ↑↑ / ↓↓ / ↑↑↑ / ↓↓↓).
- Portfolio Health 0–100 with Quality, Risk, Diversification and Stop Safety components.
- Stop Pressure (LOW / ELEVATED / HIGH / CRITICAL) based on distance to hard stop and movement toward/away from it.
- `AI WOULD DO TODAY` advisory BUY / ADD / REDUCE / SELL list. Advisory only; it does not execute trades.
- Lightweight ranking snapshots (Top 30 or portfolio+challengers) for history without storing the full universe.
- Enhanced cockpit UI with icons, arrows, penalties, health and stop-pressure detail.
- Enhanced PDF with Portfolio Health, ranking arrows, Stop Pressure, challengers and advisory actions.
- Pushover portfolio-change message now includes Portfolio Health when available.

## Persistence / capacity
- Reuses existing durable Super Portfolio state/audit storage.
- History remains capped at 180 snapshots.
- No full-universe daily snapshot is introduced.
- Correlation is evaluated only from candidate-provided correlation metadata; missing data degrades to zero correlation penalty rather than triggering extra market-data jobs.

## Version contract
- Canonical runtime version is now `v19.22.0-rc16.32b` in `app_version.py`.
- `PREVIOUS_APP_VERSION` points to `v19.22.0-rc16.32a`.
- Web header, deployment checks, reports and version contracts therefore resolve to RC16.32b instead of the inherited RC16.31ct label.

## Safety
- Shadow status retained.
- Existing Autonomy / scanner authority is unchanged.
- Manual exits remain explicit user-recorded Shadow events.

## Tests
- Added RC16.32b unit/integration coverage for sector/correlation penalties, ranking velocity, Portfolio Health, Stop Pressure, advisory actions and evaluate-state integration.
