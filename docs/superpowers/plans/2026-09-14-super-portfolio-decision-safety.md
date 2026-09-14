# Super Portfolio Decision Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add fresh-data execution gating, confidence gating, replacement hysteresis, explicit action reasons, before/after impact, and a new RC16.32i task list to Super Portfolio.

**Architecture:** Keep discovery/ranking intact and add a decision-safety layer between ranking and ordinary Shadow execution. Target selection becomes hysteresis-aware; a deterministic rebalance gate decides whether ordinary changes may execute, while emergency hard stops bypass the ordinary gate. Persist gate/impact/reason metadata for UI, PDF, diagnostics and audit.

**Tech Stack:** Python 3, dataclasses, pytest, Streamlit-compatible state payloads, existing JSON persistence.

**Spec:** `docs/superpowers/specs/2026-09-14-super-portfolio-decision-safety-design.md`

## Global Constraints
- Release version: `v19.22.0-rc16.32i`.
- Ordinary rebalance data age ceiling: 60 minutes.
- Minimum pre-trade confidence: 65/100.
- Hysteresis rank buffer: 2 positions.
- Challenger replacement margin: 2.0 adjusted score points.
- Hard-stop exits must remain immediate and must not be blocked by ordinary rebalance gates.
- No change to the two existing front-page banners.

---

### Task 1: Decision-safety tests
**Files:**
- Create: `tests/test_rc16_32i_super_portfolio_decision_safety.py`
- Modify later: `super_portfolio.py`

**Interfaces:**
- Consumes: `SuperPortfolioConfig`, `evaluate`, target-selection helpers.
- Produces: executable behavioral contract for all five RC16.32i requirements.

- [ ] Write failing tests proving stale feed blocks ordinary rebalance, low confidence blocks ordinary rebalance, hard stop still executes, hysteresis retains a near-boundary incumbent, strong challenger replaces it, every advisory action has reasons, and before/after impact is returned.
- [ ] Run `PYTHONPATH=. pytest -q tests/test_rc16_32i_super_portfolio_decision_safety.py` and confirm failures are due to missing RC16.32i behavior.

### Task 2: Decision-safety core
**Files:**
- Modify: `super_portfolio.py`

**Interfaces:**
- Produces: `select_target_rows_with_hysteresis(...)`, `build_rebalance_gate(...)`, `build_rebalance_impact(...)`, reason-enriched advisories.

- [ ] Add RC16.32i config thresholds.
- [ ] Implement hysteresis-aware target selection.
- [ ] Implement freshness + confidence gate.
- [ ] Add explicit advisory/execution reasons.
- [ ] Add before/after impact payload.
- [ ] Run the RC16.32i test file until green.

### Task 3: Scheduler freshness enforcement
**Files:**
- Modify: `super_portfolio.py`
- Test: `tests/test_rc16_32i_super_portfolio_decision_safety.py`

**Interfaces:**
- Consumes: `_rebalance_due`, `get_or_build_super_portfolio_market_pipeline`.
- Produces: scheduled AUTO rebalance always force-refreshes before an ordinary rebalance attempt.

- [ ] Add failing scheduler test.
- [ ] Implement force-refresh when AUTO rebalance is due.
- [ ] Run targeted scheduler test and full RC16.32i test file.

### Task 4: Version, release gate and new task list
**Files:**
- Modify: `app_version.py`
- Modify: `super_portfolio.py` (`master_checklist`)
- Create: `SUPER_PORTFOLIO_MASTER_CHECKLIST_RC16.32i.md`
- Create: `SUPER_PORTFOLIO_TASKLIST_RC16.32i.md`
- Create: `RELEASE_NOTES_v19.22.0_RC16.32i.md`

**Interfaces:**
- Produces: auditable release documentation and explicit backlog.

- [ ] Update version/name/history to RC16.32i.
- [ ] Add five DONE release-gate rows for implemented behavior.
- [ ] Create task list with DONE vs BACKLOG clearly separated.
- [ ] Add release notes.

### Task 5: Regression verification and packaging
**Files:**
- Package full tree and changed-files ZIP under `/mnt/data`.

**Interfaces:**
- Produces: deployable RC16.32i artifacts.

- [ ] Run all Super Portfolio RC16.32a-i tests with `PYTHONPATH=.`.
- [ ] Run `python -m py_compile super_portfolio.py app_version.py pages/super_portfolio.py`.
- [ ] Build FULL and CHANGED_FILES_ONLY ZIPs.
- [ ] Extract FULL ZIP to a clean verify directory and rerun Super Portfolio tests from the extracted package.
- [ ] Confirm packaged version string and checklist/task-list files.
