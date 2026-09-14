# SP Intelligence Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all remaining SP intelligence backlog items in one tested release.

**Architecture:** Extend the existing isolated SP engine and SP-specific discovery path. Persist candidate streak/gate metadata in SP state and keep advisory and executed Shadow actions separate.

**Tech Stack:** Python, pytest, Streamlit, yfinance-backed coarse discovery, cached public constituent pages.

**Spec:** `docs/superpowers/specs/2026-09-14-sp-intelligence-completion-design.md`

## Global Constraints
- No real-order changes.
- Hard stop bypasses ordinary gates.
- Broad USA discovery is SP-specific.
- Deep analysis remains bounded.
- TDD required for every production behavior.

---

### Task 1: Broad USA universe
**Files:** `stocks.py`, `super_portfolio.py`, `tests/test_rc16_32j_super_portfolio_completion.py`
- [ ] Write failing tests for deduplicated S&P 500 + 400 + 600 + Nasdaq-100 SP universe and >500 USA capacity.
- [ ] Run tests and verify RED.
- [ ] Implement cached broad-US constituent loaders and SP-specific resolver.
- [ ] Run tests and verify GREEN.

### Task 2: Data coverage gate
**Files:** `super_portfolio.py`, `tests/test_rc16_32j_super_portfolio_completion.py`
- [ ] Write failing tests for coverage scoring and blocking new low-coverage entrants without forced sell of incumbents.
- [ ] Run RED.
- [ ] Implement coverage metadata and executable-target filter.
- [ ] Run GREEN.

### Task 3: Candidate persistence and regime thresholds
**Files:** `super_portfolio.py`, `tests/test_rc16_32j_super_portfolio_completion.py`
- [ ] Write failing tests for consecutive fresh-run streaks and CALM/NORMAL/STRESSED thresholds.
- [ ] Run RED.
- [ ] Implement persisted streak state and regime policy.
- [ ] Run GREEN.

### Task 4: AI THINKS vs SHADOW EXECUTED
**Files:** `super_portfolio.py`, `pages/super_portfolio.py`, `tests/test_rc16_32j_super_portfolio_completion.py`
- [ ] Write failing tests for separate advisory/executed fields and visible UI labels.
- [ ] Run RED.
- [ ] Implement explicit state/snapshot fields and UI panels.
- [ ] Run GREEN.

### Task 5: Release gate and packaging
**Files:** `app_version.py`, `super_portfolio.py`, release/checklist/tasklist docs
- [ ] Write failing version/checklist tests.
- [ ] Run RED.
- [ ] Bump to RC16.32j, update checklist/tasklist/release notes.
- [ ] Run relevant and full regression tests.
- [ ] Package FULL and changed-files ZIPs and verify extracted package.
