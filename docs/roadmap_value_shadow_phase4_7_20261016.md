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

## Fase 6: Accelerated historical validation (do not wait 90 days)
- Run point-in-time walk-forward backtests over 2-3 years if as-of-date fundamentals and survivorship-aware universe membership are available.
- Reconstruct each historical candidate and its contemporaneous fundamental data; **never** apply today's P/E, financial statements or finalist rankings retrospectively.
- Compare overlapping historical rolling 7- and 30-session forward returns against contemporaneous finalists, including max drawdown.
- Keep 90-session outcomes optional and retrospective only where data already exist; do not block milestones on 90 future calendar days.
- Include transaction costs, liquidity, delistings, sector/country exposure and uncertainty; enforce separate training/test windows.
- If point-in-time historical fundamentals are unavailable, report BACKTEST_NOT_VERIFIABLE rather than inventing or presenting a successful result.
- Run a short live Shadow verification in parallel, without affecting buying, selling, ranking or deployment.
- Require documented evidence, not a fixed 90-day waiting period, before proposing production changes.

## Fase 7: Decision gate (not authorized)
- Require green CI, documented real-world evidence, independent review of risk and data quality.
- Any change to live ranking, portfolio weights, buy/sell logic or Render deployment requires separate express approval.
- This PR is diagnostics only; `can_authorize_buy=False`.

## Deterministic test scenario
A profitable, low-debt value stock at P/E 6 can score below an otherwise identical P/E 16 stock under the present quality pre-screen. The value Shadow detects the former, while existing finalist selection stays untouched. This is a synthetic regression case, **not evidence of profitable live candidates**.
