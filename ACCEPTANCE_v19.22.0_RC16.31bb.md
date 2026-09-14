# Acceptance v19.22.0-rc16.31bb

- App, scheduler and scanner use BB and the same commit.
- Existing 08:00, 14:00 and 22:00 reports remain authoritative.
- Analytical Top 3 never implies trade authority.
- Buy-ready Top 3 contains only strict candidates that pass data, evidence,
  technical timing and re-entry gates.
- NORAM-like repeated blockers become `STALLED_EVIDENCE` after three reports.
- PDF, JSON, text and Pushover show the same ticker, readiness and blocker codes.
- `DEGRADED` learning retains valid measurements and names affected tickers;
  only a failed measurement job is labelled `FEIL`.
- 20-day selected-versus-control comparison uses frozen observations and
  matching benchmark periods without future data.
- Candidate passports are idempotent and written only after the final gate.
- Same-run BUY/SELL blocking survives process-memory reset.
- Replacement candidates are fully buy-ready; no moderate recommendation can
  trigger replacement or purchase.
- Existing AY re-entry quarantine, AZ 1/5/20/60 learning and mobile report
  delivery remain intact.
- A recovering database yields `DEFERRED_DATABASE` before analysis or trading.
- A failed final status write creates `PENDING_DATABASE_REPLAY` and is replayed
  by the next healthy cron.
- `SCANNER_MAX_TICKERS=30` remains 30 across checkpoints and market changes.
- Active retention is batched, time-bounded, restart-safe and present as
  `runtime/STORAGE_RETENTION.json` in every diagnosis package.
- History labels analytical hits and buy-ready candidates separately; source
  issues are never presented as an empty pipeline error list.
- All investor and technical PDF filenames match the canonical report ID.
- Full automated suite and distribution audits pass with zero failures.
