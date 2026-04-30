# Full pipeline fix

Dette fikser hovedfeilen:
- Varsel skal bare sendes når en faktisk paper trade skjer.
- BUY signal kobles til paper_buy via auto_trade.
- SELL/stop-loss/take-profit/RSI-exit kobles til paper_sell.
- Cash, posisjoner og trade-logg holdes samlet.

VIKTIG:
Etter deploy: trykk "Reset paper portfolio" én gang for å rydde gammel inkonsistent state.
