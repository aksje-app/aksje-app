# RC16.31ab release notes

RC16.31ab bygger direkte på RC16.31aa.

- JSON fra Rapportsenteret materialiseres som varig statisk fil før nedlasting, slik at Streamlit-reruns ikke ugyldiggjør filen.
- Testkjøringer beskriver Pushover som bevisst deaktivert, ikke som manglende varslingsbeslutning.
- Teknisk PDF inkluderer komplett oppgavespor; kort PDF beholder de tre høyest prioriterte oppgavene.
- Univers-, skanne- og dekningsbegrepene er presisert.
- Alle grundig analyserte kandidater får lett primærkildekontroll av short og innsider. Bare evidenskortlisten bruker sekundær oppdagelse og full nyhetsanalyse.
- Gamle offset-naive cron-tidsstempler normaliseres til UTC før sammenligning.
- Web, rapport-scheduler og Paper-scanner publiserer faktisk versjon, Render-tjeneste og git-commit i en felles kjøretidsidentitet.
- Web varsler rødt ved versjons-/commit-avvik, diagnosepakken inkluderer identitetene, og cron kan hardstoppes med `EXPECTED_APP_VERSION`.
- Rå yfinance-404-støy dempes i Paper-cron; feil isoleres per ticker uten å stoppe resten av universet.
- Headless cron demper forventede Streamlit bare-mode-varsler.

Ingen produksjonsterskel, handelsfullmakt, risiko-, portefølje- eller schedulerregel er endret.
