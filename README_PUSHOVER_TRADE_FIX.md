# Pushover Trade Fix

Base:
- app(13).py design beholdt

Endring:
- Pushover-varsler sendes kun når faktisk paper trade skjer:
  - BUY
  - SELL
  - Stop-loss
  - Take-profit
  - Trailing stop

Ikke lenger:
- spam ved vanlig signal/refresh
- gamle UI-signalvarsler

Render ENV som brukes:
- PUSHOVER_APP_TOKEN
- PUSHOVER_USER_KEY
