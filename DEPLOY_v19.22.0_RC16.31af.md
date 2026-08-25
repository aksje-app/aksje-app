# Deploy – v19.22.0 RC16.31af

Deploy samme commit til web, rapport-scheduler og Paper-scanner.

Paper-scanner skal bruke Starter 512 MiB. Blueprint setter:

- `APP_HISTORY_CACHE_MAX_ITEMS=1`
- `APP_INFO_CACHE_MAX_ITEMS=8`
- `APP_INSIDER_CACHE_MAX_ITEMS=8`
- `SCANNER_MEMORY_SOFT_LIMIT_MB=410`

Rapporter revalideres etter én time. Kontroller etter deploy at alle tre tjenester viser samme commit og RC16.31af. En kontrollert `PARTIAL_CHECKPOINT` er en vellykket delkjøring, ikke en feil; neste cron fortsetter automatisk.
