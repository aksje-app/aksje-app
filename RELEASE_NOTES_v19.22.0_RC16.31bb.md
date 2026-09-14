# v19.22.0-rc16.31bb

BB stabilizes BA after the first live database-recovery and memory incident.
It does not lower production score, evidence, risk or paper-trading gates.

Leveransen følger kontrakten for ren distribusjon: ingen hemmeligheter,
runtime-data, brukerporteføljer eller genererte rapporter inngår i arkivene.

- Consecutive PostgreSQL health probes defer the whole cron before analysis or
  trading while the database is recovering.
- Scheduler status writes retry with exponential backoff. A final unavailable
  database produces a local replay receipt instead of an untraceable crash.
- A resumed scanner keeps its original universe and enforces the configured
  hard maximum; it never appends new tickers mid-cycle.
- Retention deletes at most 20 bounded keys or runs for 45 seconds per cron,
  defers heavier phases and publishes progress independently in diagnostics.
- Missing-report alerts use a 60-minute grace period and never warn while the
  authoritative execution owner is still active.
- Archive history separates analytical hits, buy-ready candidates, pipeline
  errors and source issues instead of labelling every score hit “recommended”.
- PDF and technical filenames use the canonical report-ID timestamp.
- Opening report details caches one canonical JSON per session and does not
  republish already durable PDF files on every Streamlit rerun.
- BA candidate passports, evidence escalation, learning controls, re-entry
  quarantine and all existing mobile delivery functions remain intact.
- No automated production parameter change or real-money trading is enabled.
