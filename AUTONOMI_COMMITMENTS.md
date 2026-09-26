# AUTONOMI_COMMITMENTS

This file is the authoritative cross-chat contract for current Autonomi work.
A chat, branch, PR description or assistant statement is not authoritative if it conflicts with this file and release_manifest.json.

## Status contract

- **AGREED** — user-approved requirement; not yet implemented.
- **IMPLEMENTED** — code exists on the current release branch.
- **TESTED** — automated/static release evidence exists and has passed in the supported test environment.
- **MERGED** — implementation is present on main.
- **DEPLOY_VERIFIED** — behavior has been verified on the deployed Render version.
- **BLOCKED** — cannot progress until the stated blocker is resolved.

Only **DEPLOY_VERIFIED** may be described to the user as fully delivered in production.

## Current deployed baseline

- Version in main before rc16.33a work: `v19.22.0-rc16.33`
- Main commit at contract creation: `4fdbf4e4c0604fce84e60325ab110590d837798a`
- Quality active model: `quality_v1.1@1.1`
- Quality V2: shadow-only; no production decision authority.

## rc16.33a completion contract

| ID | Requirement | Current status | Acceptance evidence required |
|---|---|---|---|
| QV2-001 | V2 Shadow status card on Overview with complete runs, evaluated companies, V1.1↔V2 disagreements, weakening count, next 10/25/50 milestone and decision-required state | AGREED | UI test + deployed screenshot |
| QV2-002 | Automatic V2 milestone evaluation at 10/25/50 complete runs; no indefinite shadow after 50 without an explicit decision state | IMPLEMENTED_PARTIAL | persisted milestone report + tests + deployed evidence |
| QV2-003 | Persisted V2 evaluation report explaining which components are candidates to promote, continue in shadow or revise | AGREED | generated durable report + diagnostic inclusion |
| QV2-004 | Morningstar Wide-Moat benchmark retained as a named external reference benchmark for model validation; never used as an investment instruction or copied rating authority | AGREED | benchmark dataset/reference metadata + comparison output |
| QV2-005 | Extended Quality PDF shows traceable per-stock evidence with actual periods/dates where available, not only t-0/t-1 labels | IMPLEMENTED_PARTIAL | PDF fixture/test |
| QV2-006 | Extended PDF adds charts/tables for EPS, FCF, ROCE/ROIC, margins, debt and price when data exists; explicitly says NOT DOCUMENTED when unavailable | AGREED | PDF content tests + sample PDF |
| QV2-007 | Diagnosis contains all active V1.1 and V2 inputs/outputs, model/version IDs, market-screen basis, source/fallback status, history used, thresholds/parameters, missing evidence, resource/provider failures and shadow oversight | IMPLEMENTED_PARTIAL | JSON schema test |
| QV2-008 | Sector-aware quality: banks/insurers are not forced through industrial ROCE logic; alternative evidence is explicit and conservative | AGREED | finance-sector unit tests |
| QV2-009 | Cyclical normalisation for oil/shipping/raw materials uses multi-period evidence and flags cycle-peak risk rather than treating one strong year as durable quality | AGREED | cyclical fixtures/tests |
| QV2-010 | ROIC-WACC, reinvestment and moat evidence remain NOT_DOCUMENTED unless real source data exists; no inferred/fabricated moat | IMPLEMENTED_PARTIAL | negative-evidence tests |
| QV2-011 | V2 has hard safety isolation: cannot alter active groups, BUY/HOLD/SELL, portfolio, orders or Pushover investment signals | IMPLEMENTED | invariant tests |
| QV2-012 | Quality quick action remains on Overview and return navigation works on mobile | MERGED | deploy smoke test |
| QV2-013 | Scheduled quality chain uses full fresh market prescreen before finalists and reports coverage/freshness | MERGED | deploy smoke test + diagnosis |
| QV2-014 | No release may be called GO/finished unless release_manifest.json contains evidence and all release-blocking items are at least TESTED before merge; production claims require DEPLOY_VERIFIED | AGREED | manifest gate test |

## Working rule for future chats

Before changing Autonomi, read:
1. `AUTONOMI_COMMITMENTS.md`
2. `release_manifest.json`
3. current `app_version.py`
4. current open PR / main commit relevant to the task.

Never infer completion from a prior chat. Update the two contract files in the same PR as the implementation.

## Immediate rc16.33a order

1. Contract/manifest gate.
2. Overview V2 Shadow status.
3. Durable 10/25/50 evaluation report.
4. Extended PDF/data-period improvements.
5. Diagnosis schema completion.
6. Sector/cyclical V2 shadow analysis.
7. Morningstar benchmark harness.
8. Full regression/release gate.
9. Merge.
10. Render deploy smoke test; only then mark DEPLOY_VERIFIED.
