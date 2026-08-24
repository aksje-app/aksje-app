# Endringsoversikt RC16.31ac

- `app_version.py`: RC16.31ac-identitet.
- `render.yaml`: commit-basert autodeploy for tre tjenester og automatisk klyngesamsvar for cron.
- `runtime_identity.py`: fersk versjons- og commit-sammenligning mot web.
- `scheduled_runner.py`, `paper_scanner_runtime.py`: kontrollert blokkering ved deployavvik.
- `autonomous_portfolio.py`: beskyttet observasjonsmodning og deduplisering.
- `market_intelligence.py`: synlig short-/innsiderstatus og dekningsoversikt i hoved-PDF.
- `tests/test_rc16_31ac_coordinated_deploy_learning_evidence.py`: nye regresjonstester.
