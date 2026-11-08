# Historical research: daily progress and descriptive tendency

Restore a separate short Pushover message for the broad historical parameter
research in strategy_history, not the three point-in-time archive streams or
the independent Shadow observation cohorts. Production inspection found 2,010
symbols in the universe, 1,970 acquired histories and 40 acquisition rejections.
At 11:32 UTC on 8 November, optimization had processed 887 / 1,970 symbols;
836 had complete research and 51 insufficient history per portfolio.

The normal scheduler runs the bounded summary collector immediately after
portfolio_history_optimizer. Each call reads at most 32 pairs of small stored
result documents (default 24). It does not fetch prices, rerun optimization,
read the large NOK restart bundle, or write prices, research results, portfolios,
rules or the original progress counters. Indexes are limited to 8 MiB and kept
separately per method/start cohort; hitting the limit deletes no history.

The descriptive tendency uses exactly the first finalist, ranked by the existing
training/validation selection before the untouched holdout is evaluated. It never
chooses the best holdout finalist. Require current method, ticker/portfolio,
scope, chronological split, purge and cost contracts, a finite held-out return
and actual trades. Missing/insufficient results do not become zero returns or
wins. Report positive/negative/flat counts for that candidate, and the most
frequently selected stop/holding pair, separately for the two portfolios.

One message per Europe/Oslo date, from 08:00 onward, once summary collection has
caught up. Show processed/total and the change since the last delivered report;
compare positive-share changes only within the same method/start cohort. Warn
that changing the sample can change the tendency. State the existing 0.30%
round-trip model cost and that these are exploratory exit tests, not portfolio
returns, forecasts, benchmark-relative excess, causal improvement or strategy
validation. No strategy promotion or trading rule is changed.

Pushover delivery uses the existing notifier and learning_report category.
Serialize it with the shared cross-process execution lane. Preserve daily
receipts and failed attempts; a duplicate-suppression response is not a delivery.
Retry unconfirmed delivery at most five times, spaced at least an hour apart.
Only actual successful delivery advances the comparison baseline. Stale RUNNING
source data (>8 hours) and invalid timestamps are explicit in the daily message.
Previously delivered daily messages and older method indexes remain untouched.

Validation includes bounded incremental collection, source/history preservation,
same-method cohort separation, pre-holdout selection, invalid/missing evidence,
message limits including the runtime footer, daily deduplication, failed-delivery
retry receipts, Oslo time, stale data and normal scheduler wiring. Production
acceptance additionally requires exact-source green Release Gate, live Render
deployments, actual bounded collection, preserved original data fingerprints,
and a durable successful Pushover receipt. A queued deploy is not acceptance.
