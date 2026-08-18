# Endringsinventar RC16.31x

- `services/market_snapshot_service.py`: rekursiv og total størrelsesgrense samt batchfremdrift.
- `autonomous_portfolio.py`: synlig fremdrift under snapshotbygging.
- `manual_job_background.py`: RSS-telemetri og presis restartdiagnostikk.
- `execution_coordination.py`: prosessidentitet og opprydding av foreldreløs eier.
- `app_version.py`: RC16.31x-identitet og historikk.
- `tests/test_rc16_31x_render_autonomy_memory.py`: ressurs-, restart- og 60/67-stresstester.
- Versjonssporing og obligatorisk release-dokumentasjon.
