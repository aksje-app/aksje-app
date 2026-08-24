# Deploy RC16.31ac

1. Distribuer FULL-pakken og synkroniser den eksisterende Render Blueprint én gang.
2. Kontroller at web, rapport-scheduler og Paper-scanner peker til samme repository og branch.
3. Fjern eventuell manuelt satt `EXPECTED_APP_VERSION`; automatisk commit-samsvar er autoritativt.
4. Blueprinten deployer deretter alle tre tjenester ved hver commit.
5. Verifiser at neste PDF og Pushover viser RC16.31ac og samme commit som web.

Ved midlertidig deployavvik blokkeres cron kontrollert og gjenopptas ved neste kjøring etter samsvar.
