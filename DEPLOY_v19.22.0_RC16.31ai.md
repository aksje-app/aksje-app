# Deploy – v19.22.0 RC16.31ai

1. Kopier FULL, eller kopier alt under `COPY_TO_REPOSITORY` fra DELTA til repositoryroten.
2. Ved DELTA: slett bare eksakte baner i `DELETE_FILES.txt`.
3. Commit og push til `main`. Web og `aksje-app-report-scheduler` skal bygge samme commit automatisk.
4. Kontroller at rapportplanleggeren bruker Standard (2 GiB), `python scheduled_runner.py` og intervall hvert 30. minutt.
5. Den gamle separate cronjobben som starter `python scanner_worker.py` skal fortsatt være suspendert.
6. Kjør `Trigger Run` én gang. Bekreft RC16.31ai, fullført rapportkontroll og deretter Paper-skanning uten OOM.
7. Bekreft neste faste rapport: PDF, lagring, Pushover, short/innsiderstatus og mobil retur.

Faste rapporttider er 08:00, 14:00 og 22:00 Europe/Oslo.
