# Roadmap fase 4-7: read-only value discovery and validation

## Fase 4: Diagnose (implemented in PR 100)
- Retain existing quality scores, finalist slots and production trade rules.
- Record low-positive-P/E, ROE and debt-to-equity observations in deep-value Shadow.
- Compare qualified value candidates with existing finalists; report candidates excluded by the original ranking.
- Preserve *all* missing extended factors explicitly instead of assigning artificial numbers.
- Beware that candidate_market_data currently maps `trailing_pe` from `trailingPE` **or fallback `forwardPE`;** absent a source marker the reported provenance remains unverified. Do not treat this as an audited trailing multiple.

## Fase 5: Data-quality audit (not approved for trade decisions)
- Preserve source, timestamp, reporting period, fiscal currency and units for P/E, ROE and debt ratios.
- Verify that ratio units are consistent (ROE percentage vs fraction; debt/equity units) across data providers.
- Add real-data samples and deterministic fixtures for both cheap quality businesses and value traps.
- Distinguish unavailable factors from failing factor thresholds; reject stale or contradictory inputs.

## Fase 6: Shadow outcome validation (pending observations)
- Track candidates excluded from finalists versus existing finalist/control cohorts.
- Compare forward 7/30/90-session returns and max drawdown on identical as-of dates.
- Include transaction costs, tradability/liquidity, sector/country exposure and survivorship bias.
- Record out-of-sample observations and statistical uncertainty; no outcome-based retroactive selection.

## Fase 7: Decision gate (not authorized)
- Require green CI, documented real-world evidence, independent review of risk and data quality.
- Any change to live ranking, portfolio weights, buy/sell logic or Render deployment requires separate express approval.
- This PR is diagnostics only; `can_authorize_buy=False`.

## Deterministic test scenario
A profitable, low-debt value stock at P/E 6 can score below an otherwise identical P/E 16 stock under the present quality pre-screen. The value Shadow detects the former, while existing finalist selection stays untouched. This is a synthetic regression case, **not evidence of profitable live candidates**.
