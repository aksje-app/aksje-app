# Missing morning report, 11 November 2026

The required 08:00 Europe/Oslo report started at 07:00:39 UTC. Render explicitly killed the cron at 07:13:36 UTC for exceeding its 2 GiB memory limit. Durable scheduler history contains only the start, with no report/PDF and no Pushover attempt. Report MI-20261111-080701 preparation survives, but a completed market-intelligence report does not. This is a report-generation failure, not evidence of failed Pushover transport.

At 07:12:43 the selected NOK bundle write was staged at 42,720,542 encoded bytes / 253,556,710 decoded bytes. The following committed-state read inside production_routing.autonomy completed at RSS 1271.2 MiB. A second full bundle read began at 07:13:26 with RSS already 1230.6 MiB, followed by the explicit Render memory kill. The code path is companion.complete -> load_learning_portfolio -> ensure_portfolio_separation -> production_restart.selected: a legacy migration prohibition unnecessarily decoded the entire signed financial journal while its caller retained the selected snapshot.

The migration guard now uses existing production_restart.has_selection, which reads only the small published route. Any route, including paused, foreign or malformed routes, prohibits legacy migration. An unreadable route propagates an error. No route retains the original migration path. This check grants no execution permission; signed grants, full journal verification and locked financial transactions remain unchanged. Nothing is deleted, reset or replayed by this patch.

This corrects a client/cron memory problem; the earlier compressed storage fix addressed large database writes and remains required. It is not a claim that every possible report memory peak has been eliminated.

Four new regression cases failed against the old guard and passed after correction. The no-route legacy path and unreadable-route failure are also covered. One independent final review found no Critical or Important findings. Focused PostgreSQL and final CI results are recorded in the PR.

The full local suite passed 2767 tests, skipped 268 and passed 4 subtests. The same four pre-existing local failures remain: test_production_roots_and_complete_lock_are_exact_and_installed (local installed dependency pins), test_scheduler_blocks_huge_legacy_monolith_before_payload_fetch (old FakeCursor), test_packaged_universe_is_nonempty_but_not_claimed_as_exchange_master (universe fixture), test_new_breach_sends_pushover_after_configuration_change (time-dependent FX alert). No check is relaxed.

Do not blindly rerun the morning job: its financial stage wrote before the crash. The original missing report is not silently relabeled as delivered, and a fresh report must not be presented as an 08:00 historical snapshot. Report-level production completion still requires an actual normal report and delivery receipt after rollout.

Focused checks: 41 passed without the optional PostgreSQL fixture, 62 skipped. With matching local PostgreSQL dump/restore tools, both the real upstream/learning completion integration and run-scoped signed-transaction guard integration passed against PostgreSQL 18 (2 passed). An earlier local fixture setup attempt lacked those tools on PATH; no application/test change was needed to correct the test invocation.
