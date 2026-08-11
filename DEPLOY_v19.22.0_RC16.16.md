# Deploy v19.22.0 RC16.16

1. Deploy FULL-pakken, eller legg DELTA-pakken oppå en komplett RC16.15-installasjon.
2. Restart Render-tjenesten.
3. Bekreft `v19.22.0-rc16.16`.
4. Gjør én hard nettleseroppdatering (`Ctrl+F5`) for å fjerne foreldede fragmenter fra den åpne fanen.
5. Kontroller at bare ett statuspanel vises.
6. Trykk startknappen én gang.
7. Kontroller at ny eksport-ID registreres og at statusfeltet overtar innen tre sekunder.

Hvis eksport-ID fortsatt ikke endres, hent Render-logglinjene fra tidspunktet for klikket og nettleserkonsollen. Callbacken er lokalt verifisert til å kalle `start_export()` direkte.
