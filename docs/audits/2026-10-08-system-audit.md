# System audit: decision flow, accounting, insider/short discovery and tests

Date: 2026-10-08. Baseline: `b2e66a060496dfff0b7e50274cb222eea8e76bc2`.

## Scope and limits

This audit combines repository-wide test execution with code review of the
critical Super Portfolio, Autonomi, learning, parameter approval, persistence,
scanner data acquisition and scheduler paths. It is not a claim that all 717
Python files have received an exhaustive manual review. No production holdings,
parameters, database documents or thresholds were changed during this audit.
Historical financial impact of the bugs below has not been quantified.

## Confirmed defects and fixes

| ID | Failure | Correction and evidence |
| --- | --- | --- |
| D1 | Super Portfolio tests only its preferred top-N for entry. Blocked candidates prevent lower-ranked qualified candidates from accumulating persistence or filling vacant slots. | Evaluate qualified alternatives through the same entry gates. Preserve incumbents before filling vacancies. Tests cover risk-exit refill, regular rebalance, missing coverage, stale feeds, repeated run IDs and insufficient persistence. The original implementation failed the alternative-selection scenarios. |
| D2 | With Autonomi additions enabled, a BUY overwrites the old position, applies the position cap to each order and rejects additions when the maximum number of positions is already held. | Limit the order to remaining total position capacity, accumulate quantity and weighted cost, preserve entry/stop metadata, and apply the slot count only to new holdings. All three accounting scenarios failed before the fix. |
| D3 | Execution integrity checks authorization and presence of holdings, but does not reconcile quantities and cash against starting holdings and the trade ledger. This allowed D2 to pass the integrity check. | Reconcile starting quantities and cash plus/minus each ordinary BUY/SELL/SELL_PARTIAL against the resulting portfolio. Existing cycle rollback is used on inconsistency. Tests deliberately remove shares or cash without a corresponding trade. |
| D4 | Production candidates with no measured risk/quality can inherit default risk 40 and quality 100 despite having only decision-ready flags. | The ordinary BUY path explicitly rejects missing/non-finite measured quality or risk. Two complete cycle scenarios confirmed the old behavior and now block those buys. |
| D5 | Learning exits lacking trade IDs all receive the same literal `|` identity, discarding distinct legacy exits. | Use the intended ticker/timestamp/price/P&L/reason fallback identity. Different legacy exits survive; genuine duplicates remain deduplicated. The distinct-exit test failed before correction. |
| D6 | A failed Super Portfolio subsystem is omitted from cron's overall warning derivation, allowing a clean `COMPLETED` result. | Include Super Portfolio in degraded-component reporting. Actual failure yields `COMPLETED_WITH_WARNINGS`; an expected NOT_DUE/closed market remains successful. The failure test failed before correction. |

The new scenarios are in four `test_program_audit_*` modules and included in the
release regression workflow. External snapshot/parallel services are isolated
in accounting tests; portfolio arithmetic, ordinary authorization, entry gates,
confidence and trade reconciliation are exercised by their real implementation.
One existing market-routing test was isolated from real Yahoo and insider
endpoints because its fictional symbols previously caused rate-limit timeouts.

## Verification

- All 17 original audit scenario/accounting tests and 19 event-discovery tests pass.
- Existing release contracts pass.
- Final release regression: 285 passed. Final active unversioned tests: 98
  passed. The suites overlap, so these counts must not be added together as
  a count of unique tests.
- Syntax checks and `git diff --check` pass.
- Broader diagnostic run: 1,522 passed, 96 failed, four subtests passed, with a
  five-second per-test timeout. This run preceded the final few audit tests and
  is diagnostic, not the final patch regression result.
- Same broad run on clean main: 1,509 passed, 98 failed, four subtests passed.
  All 96 failures in the audit working tree also fail on main. The two other
  baseline failures are not claimed fixed; they may depend on timing/state.

The full failure inventory is retained beside this report. A green release gate
does not imply that the entire retained historical test collection is green.
The current gate runs a selected regression suite plus unversioned tests.

## Open findings and follow-up

| ID | Finding | Required resolution |
| --- | --- | --- |
| O1 | Insider discovery previously depended on being held or reaching the finalist shortlist. Borr was absent from the 75 live finalists examined on 8 October. | This PR now adds independent Norwegian official insider and short discovery before deep/finalist selection. Borr primary-message replay passes. Remaining coverage limits: other jurisdictions, attachment-only purchase parsing, full historical backfill and exact trade-level aggregation. See the implementation section below. |
| O2 | 96 retained tests fail on both main and the audit tree. Many assert historical versions or literal UI source strings; others involve changed contracts, network calls, environment/package mismatch or behavior requiring further investigation. | Triage individual failures against current documented behavior. Replace stale textual checks with behavior tests where appropriate. Do not delete or blanket-ignore the failures to make the suite green. The inventory records exact test names and messages. |
| O3 | The broad test collection can access live providers, reuse local process/storage state, and hang in external calls. This can hide defects and make results depend on test order or provider availability. | Isolate external providers and runtime storage for deterministic tests; retain separate bounded integration checks. The audit uses explicit timeouts and a clean baseline checkout. |
| O4 | Transitive dependencies installed from requirements.txt differ from requirements.lock. The deterministic dependency check failed in the audit environment. | Run that check in a lock-installed environment and verify CI/web/cron installation consistency before treating dependency closure as proven. No service configuration or package upgrades were made here. |

## Release status

The fixes are prepared for review. This report does not certify the entire
program as error-free or production-ready, and it does not claim that the open
international/attachment-only discovery gaps or all historical test failures have been resolved.


## Added to PR #65: independent insider and short event discovery

`market_event_discovery.py` polls the official Oslo NewsWeb PDMR category and
Finanstilsynet's public short register before portfolio finalist selection.
The scheduler checks the persisted feed on its normal cycle, with a 15-minute
poll cache. New matched events and same-day short-register revisions invalidate an otherwise fresh 12-hour portfolio
feed. No source query depends on a ticker reaching the shortlist first.

- Resolve Oslo issuer symbols, exact ISINs or unique normalized issuer names
  against the investable Norwegian universe. Ambiguous identities remain unmatched.
- Reserve at most ten slots within the existing deep-analysis budget. Alternate
  insider and short families so bearish short activity can also trigger analysis.
  Events beyond the budget are explicitly `DEFERRED_ANALYSIS_LIMIT`; this is not
  a guarantee that every event receives immediate analysis.
- Keep normal investment scores, finalist ranking, production-market policy,
  position caps, persistence, freshness, coverage and risk/re-entry gates. An
  insider purchase or reduced short does not authorize a purchase.
- Classify a purchase only from an explicit supported official purchase sentence.
  Keep other PDMR notifications unclassified. Extract close-associate evidence
  from that sentence rather than hardcoding a Trøim/Borr exception. Group repeated
  confirmed purchase announcements over 30/90 days by issuer, buyer and currency;
  these are announcement counts, not inferred individual fills. Use publication
  time, not a guessed trade time. Never sum different currencies together.
- Compare each short actor between consecutive official snapshots: new public
  position, increased, reduced, or below-public-threshold/unknown. First snapshot
  is a baseline. Actor disappearance is not reported as zero or full covering.
  Public aggregated positions are not total short interest or short-sale volume.
- Deduplicate official identities, supersede corrected insider disclosures,
  rotate failed detail requests, retain previous evidence on source failure,
  and prevent evidence observed after a replay time from entering that replay.
- Persist with StorageService's atomic document mutation. Bound responses to
  2 MB, requests to 15 seconds, each refresh to a 45-second request budget, and
  detail fetches to six. Retain at most 2,000 events for 90 days. Overflow,
  outstanding details and unavailable sources remain visible; absence of data
  is not proof of absence of transactions.
- Display source status, official events, analysis/finalist status and repeated
  purchase clusters in one expandable Super Portfolio section.

### Primary-source replay and live read-only verification

The fixture `tests/fixtures/market_events/borr_683610.json` was obtained from
NewsWeb's official message endpoint, using the API URL published by NewsWeb's
`urls.json`. Message 683610, published 6 October 2026, explicitly identifies
Drew Holdings Ltd. as Trøim's close associate and reports 1,500,000 purchased
shares at USD 4.1314. The replay proves that BORR.OL reaches fresh analysis even
when absent from the coarse shortlist, while a better-scoring ordinary candidate
still wins the single finalist slot. It does not claim that historical production
would have bought Borr or quantify financial impact.

A read-only live adapter check on 8 October fetched 639 normalized events in
memory, with short source `OK` and insider source `PARTIAL` (detail failures and
remaining documents). Two Borr disclosures were classified as explicit purchases;
two remained notifications awaiting detail classification. No production database
or portfolio was written by that check. The short timeout experiment initially
failed at four seconds; the final bounded adapter uses the limits above.

Primary sources:
- https://newsweb.oslobors.no/urls.json
- https://newsweb.oslobors.no/message/683610
- https://ssr.finanstilsynet.no/api/v2/openapi.json
- https://ssr.finanstilsynet.no/api/v2/instruments

### Explicit remaining limits

This independent event feed currently covers Norway only; Sweden, Denmark,
Finland and USA still use the existing finalist/held-name checks. Insider polling
covers the last seven days and accumulates retained history after deployment;
there is no complete 90-day initial backfill. Generic PDMR PDFs/tables, option
exercise, grants, buybacks, loans, redelivery and ambiguous transfers are not
converted into verified discretionary purchases. Exact transaction dates,
individual fills and global entity aliases need additional verified adapters.
Short disappearance can reflect falling below the public threshold and must
remain unknown as to actual remaining exposure. More than ten event issuers
can be deferred; no complete latency SLA is claimed.

Nineteen deterministic event tests cover primary Borr replay, unboosted finalist
selection, real entry-persistence rejection, short actor changes/unknown exits,
ambiguous issuer matching, observed-time replay protection, correction/deduplication,
currency-separated aggregation, failed-source retention, partial feeds, request
limits, failed-detail rotation, same-day register corrections and cache invalidation. The test module is included
in the release gate. UI rendering on a real mobile browser has not been certified.
