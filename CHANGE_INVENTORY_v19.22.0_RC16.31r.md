# Endringsinventar RC16.31r

## Kode

- `autonomous_portfolio.py`: prosessisolert parallell strategivurdering, hard timeout og kontrollert fail-open.
- `parallel_strategy_isolated_worker.py`: ny avgrenset worker for observational strategisammenligning.
- `manual_job_background.py`: sannferdige felter og meldinger for publiseringslease, worker og rapportlås.
- `autonomy_overview.py`: misvisende løfte om frigitt lås/ny kjøring fjernet.
- `market_intelligence.py`: STALLED vises som stoppmerket, ikke frigitt.
- `app_version.py`: RC16.31r-versjonskontrakt og changelog.

## Tester

- `tests/test_rc16_31r_parallel_timeout_and_lock_truth.py`: timeout-, watchdog-, manuell lease- og distribusjonsregresjoner.
- Eldre versjonskontrakttester er oppdatert til RC16.31r med RC16.31q som direkte forgjenger.

## Dokumentasjon

- Release notes, akseptanse, deploynote, valideringsrapport, buildresultat og dette inventaret.

Ingen produksjonsterskler, handelsporter, risiko-/porteføljeregler eller faste rapporttidspunkter er endret.

