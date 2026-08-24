# Deploy RC16.31ab

1. Distribuer FULL-pakken eller bruk DELTA på en verifisert RC16.31aa-installasjon.
2. Behold eksisterende Render-miljøvariabler, PostgreSQL og 2 GiB Standard-instans. Sett `EXPECTED_APP_VERSION=v19.22.0-rc16.31ab` på alle tre tjenester.
3. Distribuer web `aksje-app`, `aksje-app-report-scheduler` og `aksje-app-paper-scanner` manuelt fra samme branch og commit. En opplastet ZIP alene oppdaterer ikke nødvendigvis alle tjenestene.
4. Kontroller at header viser `v19.22.0-rc16.31ab` og at intet rødt distribusjonsavvik vises.
5. Kjør ett utkast og verifiser stabil JSON-nedlasting, kort PDF og full teknisk PDF.
6. Verifiser at short og innsider ikke står `IKKE SØKT` for kandidater som støttes av markedets primærkilde.
7. Verifiser neste planlagte rapport og at Pushover viser `v19.22.0-rc16.31ab`, korrekt tjeneste og samme commit som web.

Rollback: distribuer uendret RC16.31aa FULL-pakke. Historiske rapporter og snapshots skal ikke slettes.
