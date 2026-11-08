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
wins. Retain positive/negative/flat counts and the most frequently selected
stop/holding pair in the stored evidence, separately for the two portfolios.

One message per Europe/Oslo date, from 08:00 onward, once summary collection has
caught up. The short message uses everyday Norwegian: how many stocks have been
examined, how many more since the last message within the same method/start
cohort, and how often the historical tests produced a gain for each portfolio.
For at least 100 measured stocks, express this as approximately X out of 100;
for smaller samples use the actual counts. Explain that this describes how
often tests made a gain, and better real trading remains unproven. State that
the user's trading rules are unchanged. No strategy promotion is allowed.

Keep technical method names, percentage-point changes, modal stop/holding
parameters, slash-separated missing-data counters, UTC stamps and model-cost
notation out of the Pushover copy. The evidence, existing 0.30% cost assumption,
candidate selection, measurement rules and original receipts stay intact.
Only genuine missing/stale progress adds a short plain-language warning.

## Gain magnitude and combinations

The count of stocks with a positive result alone does not describe the size of
gains or losses. Show the mean percentage return per completed simulated trade,
including losing trades and the existing 0.30% round-trip cost. Read the actual
first finalist's holdout avg_pct and trades; weight each stock's mean by its
actual trade count. Never divide a compounded total return by the number of
trades or imply that it is a per-trade or annual return. Missing avg_pct remains
missing and its reduced measurement coverage is explicit.

Show the two most frequently preselected stop/holding combinations separately
for each portfolio, explaining them as selling on a specified fall or after a
specified number of trading days. Give the mean per trade for each combination
and the number of stocks providing that measurement. Sort by selection count,
not holdout profit. These groups contain different stocks selected in training;
they cannot establish which combination is best on a common universe. Do not
call them a ranking or an automatically recommended trading rule.

Cache the enriched evidence under a separate indexes/results-v2 path. Keep the
earlier cache, all original research/price data, previous notifications and
trading rules. Collection remains bounded to 24 pairs per cron, maximum 32;
completed measurements are reused without price downloads or large financial
journal reads. Per-trade gains, source digests and counts are retained for audit.

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
