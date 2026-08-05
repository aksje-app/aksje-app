# Akseptanse v19.22.0 Investor Edition RC2

## Lokal akseptanse
- ZIP-integritet skal være bestått.
- Python-kompilering skal være bestått.
- Hele lokale pytest-pakken skal være bestått.
- Statisk releaseaudit skal være bestått.
- Ingen endring skal finnes i `final_score`, kandidatvalg, scheduler, innlogging eller handelsregler.
- FULL, DELTA, deploynotat, valideringsrapport, endringsoversikt og SHA-256 skal leveres.
- DELTA-slettelisten skal ikke inneholde `.app_runtime`, cache, logger, hemmeligheter eller andre mutable lokale filer.

## Live akseptanse på Render
Følgende kan ikke godkjennes lokalt og må dokumenteres etter deploy:
- innlogging/utlogging og navigasjon i faktisk UI
- Rapporter rett etter Oversikt
- synlig og fungerende `Kjør nytt utkast`
- kompakte rapportknapper uten uønsket fullbredde-CSS
- samsvar mellom UI, JSON og PDF
- scheduler 08:00/22:00 og Pushover uten manuell forkjøring
- varig minste varsel-score fra neste kjøring

## Produksjonsstatus
RC2 er ikke produksjonsklar før live akseptansepunktene er bestått på Render.
