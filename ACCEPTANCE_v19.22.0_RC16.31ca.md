# Acceptance - RC16.31ca

## Must pass
- [ ] Web, scheduler and paper scanner run `v19.22.0-rc16.31ca` on the same commit.
- [ ] Complete manual report reaches terminal `COMPLETED` and release gate PASS.
- [ ] Norway universe remains authoritative and 294/294 when the verified Euronext snapshot is current.
- [ ] Unified **Rapportfiler** area exposes Standard PDF, Technical PDF, JSON and Diagnostic ZIP for a completed manual run.
- [ ] Complete report ZIP contains both PDFs and JSON; manual-run ZIP also contains the diagnostic ZIP when durable diagnostics exist.
- [ ] Recommendation, observation and rejection tables use specific exchange names when available.
- [ ] A pre-open observation waiting for the next trading day is not reported as missing/stale series.
- [ ] Progress remains monotonic and no manual refresh is needed.
- [ ] Memory remains safely below the 2 GiB container ceiling during a 294-share run.

## Still requires live production evidence
- Ordinary 08:00 / 14:00 / 22:00 runs.
- Current evidence/source coverage and any genuine insider/news source failures.
