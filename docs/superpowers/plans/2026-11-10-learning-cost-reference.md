# Source-bound learning cost reference implementation plan

> Implement inline, using existing authorized continuation. Independent review before merge.

**Goal:** Finish the cost-measurement preparation in point 2 without starting point 5 or inventing historical trades/FX.

**Architecture:** Reuse `services.trading_costs` and `economic_ledger.fx_rate` in the existing V2 observation engine. An immutable definition plus a small publication receipt are recorded by existing scheduled maintenance before the modeled entry opening. Each new horizon may carry a separate costed total-return reference; actual net portfolio performance stays unverified. No new worker, quote request, scan, trade or historical backfill.

**Tech Stack:** Python, existing PostgreSQL immutable JSON, pytest.

## Design and choices

- Reuse the already approved Autonomy model policy: 20 bp per buy/sell and 25 bp on each modeled foreign-currency conversion. This is explicitly an Autonomy cost reference, not Super Portfolio costs or observed brokerage. The exit-grid research's 30 bp per test trade remains separate.
- Prefer documented supplied FX over daily indicative substitution. Foreign modeled entries/exits require matching source-bound quotes no more than 15 minutes before each endpoint. Missing/future/stale/mismatched FX stays unqualified, not zero. No new provider integration.
- Model one normalized total-return unit, using the existing adjusted-return proxy and entry/exit proportional costs. Preserve the approved source policy in the contract. The model assumes gross provider reinvestment inside the return unit, no intermediate reinvestment fees and no tax. These limitations are explicit; no actual fill/dividend-cash/portfolio claim.
- Record the contract's actual time and release commit before entry. A late/missing/changed contract cannot qualify a historical observation. Read-only UI never writes it. Existing scheduled maintenance is the only automatic binder, on authoritative PostgreSQL.
- Preserve all frozen readings. If newly supplied data changes an already costed reference, reject it as history revision. If current FX disappears, retain the original frozen reference. An unqualified frozen horizon is not silently backfilled later.
- All 41 currently pending V2 rows have documented NOK currency and no completed horizons. This change may prepare their future cost references; it does not produce results now.
- Legacy rows remain frozen and quarantined rows remain untouched. No original snapshot rewrite. `net_return_pct` and `net_result_verified` retain their existing actual-result semantics (null/false).

## Review focus

1. Cost double charging, percentage denominators and different FX entry/exit values.
2. Contract after entry, altered policy/provenance or unknown release identity.
3. Missing/boolean/nonfinite currency/FX/price values; no indicative FX masquerading as a timestamped endpoint quote.
4. Frozen references, missing new FX and old unqualified horizons must not be rewritten.
5. Reports must use STRICT-only qualified cost references with sample counts; source absence never becomes zero return or verified portfolio profit.

## Task 1: Pure accounting and immutable pre-entry contract

- [ ] Tests first in `tests/test_learning_cost_reference.py`: NOK fees, foreign FX and fees, missing/stale/future/wrong FX, invalid currency, late/altered contract, real PostgreSQL immutable/idempotent binding.
- [ ] Add `services/learning_cost_reference.py` with `ensure_contract(storage, commit, clock=None)`, `validate_contract(contract, before)`, `cost_reference(...)` and read-only summary/replay validation. Reuse existing economic/cost functions and approved source identifiers. Restrict the normalized-unit model to its pinned proportional policy.
- [ ] Observe failures, implement, run focused tests and commit.

## Task 2: Existing engine and reports

- [ ] Tests first: measurement attaches separate reference; original snapshot unchanged; frozen reference revisions rejected; non-qualified FX stays null; maintenance binds before evaluation; previews never bind; summary excludes legacy/control/unverified/tampered blocks.
- [ ] Integrate into V2 `measure`, preserving source endpoint time and optional supplied FX quote fields. Load contract once per evaluation; bind only in existing scheduled maintenance. Store a small cost-reference block, not a repeated full contract.
- [ ] Add clearly labeled STRICT 20-session model reference/count to existing report control/PDF/weekly views. Keep actual net/strategy validation false and report missing input counts.
- [ ] Run focused PostgreSQL tests, relevant browser/PDF checks and repository suite; record baseline failures by name. Add file to existing PostgreSQL release check.

## Task 3: Review, exact-head release and production proof

- [ ] Independent review; reproduce/fix important findings with tests.
- [ ] Exact-head Release Gate, merge, deploy web/cron without extra scans. Verify normal scheduled maintenance recorded the immutable contract before next entry, source preservation, health and commit.
- [ ] Update issue 196 and closeout/recovery evidence. Historical sources and first nonzero production signal remain explicit open items if not observed; point 5 stays paused.

## Ledger

Continuation is already authorized; existing policy terms are not changed. The conservative choice is to leave foreign net references unavailable without endpoint FX, rather than fabricate indicative execution rates. Gross provider proxy and actual portfolio profit remain separate.

Ruling: publication uses a wall-clock bound captured after the immutable definition transaction returns, with a separate immutable receipt. The scheduler start clock is not publication evidence. A delayed definition write crossing the entry opening remains unqualified (real PostgreSQL regression).

Ruling: this reference qualifies forward V2 measurements only. A retrospective study in point 5 needs its own predeclared study/split contract; this change does not backdate a new method to historical entries. It can reuse the existing approved economic calculator without relabeling past observations as prospective evidence.

Ruling: optional cost-source read failure leaves model values unavailable and explicitly counted. Valid gross evidence remains available; no missing value is zero, and frozen unqualified horizons are not silently rewritten later.

Task progress: pure accounting, publication, V2 integration, frozen FX behavior and read-only report regressions passed. 110 focused tests passed with isolated PostgreSQL; full local suite:2710 passed,236 skipped,4 subtests,4 previously documented baseline failures. Model references remain pretax provider reinvestment proxies, never actual portfolio profit.
