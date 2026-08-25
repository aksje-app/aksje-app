# Deploy – v19.22.0 RC16.31ah

1. Kopier FULL, eller kopier `COPY_TO_REPOSITORY` fra DELTA til repositoryroten.
2. Ved DELTA: slett alle eksakte baner oppført i `DELETE_FILES.txt`. Dette er kun historiske dokument- og resultatfiler.
3. Commit og push til `main`; web og rapportplanlegger skal auto-deploye samme commit.
4. Bekreft at `aksje-app-report-scheduler` fortsatt bruker Standard med 2 GiB og starter `python scheduled_runner.py`.
5. Suspender den gamle separate 512 MiB-jobben som starter `python scanner_worker.py`.
6. Kjør `Trigger Run` på rapportplanleggeren og bekreft rapportkontroll etterfulgt av Paper-scanning uten OOM.
