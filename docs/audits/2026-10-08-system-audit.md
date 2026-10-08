# System audit: decision flow, accounting and test coverage

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

- All 17 new scenario/accounting tests pass.
- Existing release contracts pass.
- Final release regression: 266 passed. Final active unversioned tests: 79
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
| O1 | Insider discovery runs after coarse/finalist selection and only checks held names plus five finalists per market. Borr was absent from the live 75 finalists examined on 8 October. A 24-hour cache also limits repeated-purchase detection. | Add bounded official announcement ingestion independent of ranking, entity/ticker alias resolution, repeated-purchase aggregation and candidate re-analysis. Do not lower risk gates or automatically buy because of an insider purchase. This architecture change is not implemented in this patch. |
| O2 | 96 retained tests fail on both main and the audit tree. Many assert historical versions or literal UI source strings; others involve changed contracts, network calls, environment/package mismatch or behavior requiring further investigation. | Triage individual failures against current documented behavior. Replace stale textual checks with behavior tests where appropriate. Do not delete or blanket-ignore the failures to make the suite green. The inventory records exact test names and messages. |
| O3 | The broad test collection can access live providers, reuse local process/storage state, and hang in external calls. This can hide defects and make results depend on test order or provider availability. | Isolate external providers and runtime storage for deterministic tests; retain separate bounded integration checks. The audit uses explicit timeouts and a clean baseline checkout. |
| O4 | Transitive dependencies installed from requirements.txt differ from requirements.lock. The deterministic dependency check failed in the audit environment. | Run that check in a lock-installed environment and verify CI/web/cron installation consistency before treating dependency closure as proven. No service configuration or package upgrades were made here. |

## Release status

The fixes are prepared for review. This report does not certify the entire
program as error-free or production-ready, and it does not claim that the open
insider-discovery gap or all historical test failures have been resolved.
