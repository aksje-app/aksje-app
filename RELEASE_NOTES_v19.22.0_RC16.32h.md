# Release Notes — v19.22.0 RC16.32h

## Super Portfolio Diagnostics

- Manuell `Vurder porteføljen nå` tvinger nå en fersk Super Portfolio market-feed (`force_refresh=True`) i stedet for å gjenbruke 12-timers cache.
- Progressbaren drives av faktiske markedssteg: univers lastet, grovscan, dypanalyse og ferdig marked.
- Ny `Decision Trace` lagres for samme beslutnings-run og viser per aksje: eksisterende posisjon, run-ID, pipeline-medlemskap, eligibility, rank/score, målvekt, AI-handling og eksplisitt eksklusjonsårsak.
- `INCONSISTENT_DECISION` og `SNAPSHOT_MISMATCH` flagges når SELL ikke kan forklares konsistent av samme beslutningsgrunnlag.
- Ny UI for `🔎 Diagnostiser valgt aksje` og `📦 Last ned diagnose-ZIP`.
- Diagnose-ZIP inneholder README, beslutningsspor, valgt aksje, state-sammendrag og AI WOULD DO TODAY-data.
- Ingen handels-/rangeringsregler er endret i denne releasen.
