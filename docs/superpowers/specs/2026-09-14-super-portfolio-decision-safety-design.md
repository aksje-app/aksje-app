# Super Portfolio Decision Safety Design

## Goal
Make SP rebalancing auditable and safer: ordinary Shadow BUY/SELL/ADD/REDUCE may only execute from fresh same-run data, with sufficient decision confidence and meaningful replacement advantage; every action must carry an explicit reason, and the user must see the before/after portfolio impact.

## Scope
This is RC16.32i. It does not alter hard-stop emergency exits, the multi-market discovery funnel, the two-banner front-page contract, or production Norway-only isolation.

## Design

### 1. Freshness gate
- Ordinary Shadow rebalancing requires a non-empty market-feed run id.
- Market-feed `created_at` must be no older than 60 minutes at decision time.
- The decision trace, target portfolio and executed changes must use the same run id.
- A stale/invalid feed blocks ordinary rebalance with a visible gate reason; hard-stop exits remain allowed.
- Scheduled AUTO runs that are due to rebalance must force-refresh the SP market feed before evaluating.

### 2. Confidence gate
- Before ordinary rebalance, calculate a pre-trade confidence score from selected candidates: average data-quality, feed freshness, regime-fit, score agreement/spread and correlation availability.
- Minimum confidence for ordinary rebalancing is 65/100.
- Below threshold, ordinary rebalance is blocked and advisory actions remain visible; hard-stop exits remain allowed.

### 3. Replacement hysteresis
- Existing eligible holdings just outside Top-10 receive a rank buffer of two places.
- A new challenger must beat such an incumbent by at least 2.0 adjusted score points to force replacement.
- This affects target selection only; it never protects a hard-stop position or an ineligible/missing candidate.

### 4. Explicit reason codes
Every advisory and executed action must include `reason_code` and human-readable `reason`.
Canonical codes for this release:
- `NEW_TOP_CANDIDATE`
- `CHALLENGER_WIN`
- `TARGET_WEIGHT_INCREASE`
- `TARGET_WEIGHT_DECREASE`
- `OUTSIDE_TARGET_TOP_N`
- `HYSTERESIS_HOLD`
- `CONFIDENCE_GATE_BLOCKED`
- `FRESHNESS_GATE_BLOCKED`
- existing `HARD_STOP` and `MANUAL_EXIT` remain unchanged.

### 5. Before/after impact
Each evaluation stores and returns a `rebalance_impact` object containing:
- current Portfolio Health
- projected Portfolio Health using target rows/weights
- health delta
- current/projected correlation component
- current/projected risk component
- proposed turnover estimate
- gate status and reasons

The UI/PDF may consume this object without recalculating portfolio logic.

## Release gate / task list
RC16.32i master checklist adds explicit items for freshness gate, confidence gate, replacement hysteresis, action reason codes, and before/after impact. A separate RC16.32i task-list markdown file records these five as release requirements and keeps candidate persistence, regime-aware thresholds and per-stock data-coverage gating as future backlog, not falsely marked complete.

## Testing
Use TDD. Add targeted unit tests for each gate and hysteresis behavior, verify hard-stop behavior remains immediate, then run all Super Portfolio RC16.32a-h regression tests, compile changed Python files, and verify packaged ZIP contents/version.
