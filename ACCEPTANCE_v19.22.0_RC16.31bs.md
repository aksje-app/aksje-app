# Acceptance – RC16.31bs

RC16.31bs can be accepted live when:

- [ ] Runtime identity is `v19.22.0-rc16.31bs` for web, scheduler and Paper scanner.
- [ ] A report exposes candidate total, evidence-controlled count, evidence-ready count and not-prioritized count.
- [ ] `evidence_ready <= evidence_controlled <= candidate_total`.
- [ ] The report-facing percentage equals `evidence_ready / evidence_controlled`, not `evidence_ready / candidate_total`.
- [ ] Example semantics are clear: 13 ready of 20 controlled = 65%, while 53 of 73 were not prioritized for full evidence control.
- [ ] Legacy `candidate_evidence_coverage` remains available for compatibility but is not presented as the main quality score.
- [ ] No regression in Norway complete-universe, Fresh Trend, Paper Trade, terminal status or manual-report memory behavior.
