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
scope, chronological split, purge and cost contracts, finite held-out total and
average returns and actual trades. Missing/insufficient results do not become zero returns or
wins. Retain positive/negative/flat counts and the most frequently selected
stop/holding pair in the stored evidence, separately for the two portfolios.

One message per Europe/Oslo date, from 08:00 onward, once summary collection has
caught up. The short message uses everyday Norwegian: progress since the previous
message, average percentage gain/loss per test trade after the existing 0.30%
round-trip cost, including losing trades, and how many stocks had a positive
total result. Show sample sizes (trades and stocks), separately for each portfolio.
Show the two most frequently selected stop/holding pairs with their own average
and sample sizes. Order pairs by selection frequency, then stop/holding values
to break ties, never by their holdout performance.

Use held-out `avg_pct` from the first finalist and weight it by its `trades`.
This is the arithmetic average of all net trades; compounded `total_pct` divided
by trades is not a per-trade return. Do not subtract the cost a second time.
Store aggregates for every selected pair in the summary. Pair results describe
different selected subsets of stocks and periods; they cannot prove which rule
is best. Explain that sales happen at the stop or after the stated exchange
sessions, that most common does not mean best, and that these historical tests
are not annual or portfolio returns or a forecast. Trading rules are unchanged.
Keep technical method names and UTC counters out of the Pushover copy.

Notification index version 2 uses `indexes/v2/<cohort>.json` so existing stored
results are reread in bounded batches to obtain the average, without changing
the original index or optimizer. Keep cohort identity unchanged for progress
comparisons. Do not send until collection has caught up. Existing daily delivery
receipts remain authoritative; deploying this change does not resend that day.
The existing 0.30% cost assumption, candidate selection and source data stay intact.
Only genuine missing/stale progress adds a short plain-language warning.

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
