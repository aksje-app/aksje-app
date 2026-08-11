# Deploy v19.22.0 RC16.15

1. Deploy FULL-pakken, eller legg DELTA-pakken oppå en komplett RC16.14-installasjon.
2. Restart Render-tjenesten.
3. Bekreft at appen viser `v19.22.0-rc16.15`.
4. Åpne komplett rapport-, replay- og læringsarkiv.
5. Trykk startknappen én gang.
6. Kontroller at en grønn kvittering med en ny eksport-ID vises umiddelbart.
7. Kontroller at statusfeltet viser den samme eksport-ID-en innen tre sekunder.
8. Kontroller videre watchdog-heartbeat, timeout/karantene og ferdig ZIP.

Hvis ingen grønn kvittering vises, har selve Streamlit-formhendelsen ikke nådd serveren; registrer nettleserkonsoll og Render-logg før en ny kodeendring.
