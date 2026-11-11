# Pushover direct PDF Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore native PDF viewing from Pushover, with the existing file download page as reserve.
**Architecture:** Pinned public st.App custom route and a small root-entry redirect middleware, backed by existing durable PDF validation. UI opt-in and notifier URL conversion keep the two entry purposes explicit.
**Tech Stack:** Python, Streamlit1.57 st.App, Starlette, pytest, actual local web_runner.
**Spec:** docs/superpowers/specs/2026-11-11-pushover-direct-pdf-design.md

## Global Constraints

- No guessed PDF, static-file dependency, new worker/storage, financial replay, notification resend, weaker token validation or physical iPhone success claim.
- Preserve health, startup heartbeat, app navigation, report expiry and original PDF bytes.

## Review Focus

- Wrong/multiple/encoded token input must not expose another file or redirect externally.
- HEAD/ranges/Unicode filenames must work without HTML/PDF corruption.
- Storage failure must not fall back to an expired local file or block health.
- Existing Pushover links must open PDF; explicit in-app report links must retain their page.
- Cold restart and actual configured launcher must serve direct PDFs without an app session.

### Task1: Durable inline PDF entry

Files: public_pdf_http.py, web_app.py, web_runner.py; tests/test_public_pdf_http.py and tests/test_web_runtime_heartbeat.py.
Interfaces: consumes public_report_store.load_public_pdf(token); produces direct PDF GET/HEAD route and root report redirect middleware.
- [x] Write HTTP regressions, observe RED.
- [x] Implement inline PDF with validated bytes, expiry and error handling, bounded single-range parsing; public st.App launcher and existing heartbeat.
- [x] Verify HTTP tests and actual launcher/cold restart against isolated local storage.

### Task2: Delivery and UI intent

Files: report_delivery.py, notifier.py, public_report_ui.py; tests/test_public_pdf_http.py, browser/return regressions.
Interfaces: same-origin report URL -> direct .pdf for Pushover; report_view=page for UI reserve.
- [x] Write URL/intent regressions, observe RED.
- [x] Implement narrow URL conversion and explicit fallback page intent, preserving unrelated URLs.
- [x] Run focused, browser and complete checks; one final independent review; fix important findings before opening PR.
- [ ] One exact-head CI, merge/deploy, actual production PDF/old-link/fallback checks. Record physical phone confirmation as pending rather than claiming success.

Final review: one independent whole-branch review. Important notifier fingerprint drift was reproduced RED and fixed GREEN by normalizing only outgoing payload URL. The secondary download-page link finding was regraded Important because preserving that named fallback is part of the requested flow; reproduced RED and fixed GREEN with explicit page intent. Final focused61 passed;4 browser cases passed; complete local suite2787 passed,270 skipped,4 subtests passed and the same4 pre-existing failures (dependency-lock installed pins, old FakeCursor, packaged-universe authority fixture, time-dependent FX alert). No workflow checks relaxed.
