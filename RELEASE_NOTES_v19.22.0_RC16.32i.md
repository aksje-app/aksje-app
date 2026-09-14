# Release Notes – v19.22.0-rc16.32i

## Super Portfolio Decision Safety

- Freshness gate: ordinary Shadow rebalancing requires market-feed age <= 60 minutes and a valid decision run ID.
- Scheduled AUTO rebalance due-runs force a fresh SP market scan before execution.
- Decision Confidence gate: ordinary rebalance requires >= 65/100.
- Replacement hysteresis: incumbents within two ranks of the Top-10 boundary are retained unless a challenger wins by at least 2.0 adjusted-score points.
- Advisory and executed BUY/ADD/REDUCE/SELL actions carry explicit `reason_code`, `reason`, and `decision_run_id`.
- Every evaluation stores `rebalance_impact`: before/after Portfolio Health, risk component, correlation component, turnover and gate status.
- Hard-stop exits remain immediate even when ordinary rebalance is blocked.
- New `SUPER_PORTFOLIO_TASKLIST_RC16.32i.md` separates completed work from future backlog.
