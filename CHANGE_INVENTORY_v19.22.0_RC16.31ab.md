# Endringsoversikt RC16.31ab

- `app_version.py`: RC16.31ab-identitet og endringslogg.
- `market_intelligence.py`: varig JSON-nedlasting, Pushover-tekst, komplett teknisk oppgavespor og forklaring av dekning.
- `investment_pipeline.py`: lett short-/innsidergrunnkontroll utenfor evidenskortlisten.
- `insider_intelligence.py`: primærkildebegrenset innsiderkontroll.
- `cron_control.py`: UTC-normalisering av gamle og nye lagrede tidsstempler.
- `runtime_identity.py`: felles, varig tjeneste-/versjons-/commit-identitet og forventet-versjon-gate.
- `scheduled_runner.py`, `paper_scanner_runtime.py`, `scanner_worker.py`: identitets-heartbeat, headless logging og isolert markedsdatafeil.
- `app.py`: synlig kritisk varsel ved ulik versjon/commit mellom Render-tjenestene.
- `manual_job_background.py`: kjøretidsidentiteter i diagnosepakken.
- `tests/test_rc16_31ab_report_delivery_evidence_baseline.py`: regresjonstester for nedlasting, datadekning, tidssone og kjøretidsidentitet.
- Berørte versjons- og pipeline-tester er oppdatert til den nye kontrakten.
