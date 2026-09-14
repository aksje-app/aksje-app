# Acceptance v19.22.0-rc16.31bd

## Lokal acceptance
- Python bytecode compilation: PASS.
- RC16.31bd målrettede production-closure tester: PASS.
- Retention True-parsing, bounded APPLY, database fail-closed, scanner storage-finalization classification, truthful aggregate status, production-closure receipt og paper-portfolio no-fallback: PASS.
- FULL/DELTA struktur- og sikkerhetsvalidering skal være PASS før levering.

## Live acceptance på Render
Produksjonsstatus settes først når:
- web og scheduler kjører samme versjon/commit,
- PostgreSQL er autoritativ og stabil,
- retention faktisk sletter i bounded batcher,
- én ordinær scanner-syklus er frisk,
- obligatoriske 08:00, 14:00 og 22:00 rapporter er komplette,
- PDF/JSON er persistente og Pushover leverer,
- ingen dublett, lokal produksjonsfallback eller uavklart recovery-receipt finnes.
