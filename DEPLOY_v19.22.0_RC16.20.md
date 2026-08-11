# Deploy v19.22.0-rc16.20

1. Last opp hele FULL-pakken til GitHub, inkludert `assets/`.
2. Deploy/restart Render etter at commit er bygget.
3. Utfør Ctrl+F5 én gang etter at Render viser deploy fullført.
4. Åpne Autonomi → Rapporter → Fullt rapportsenter.
5. Start én utkastkjøring og kontroller at «Siste reelle fremdrift» endres.
6. Test avbrudd på en ufarlig testkjøring. Etter 60 sekunder uten fremdrift skal sikker frigivelse tilbys; PREFLIGHT frigjøres automatisk senest etter 150 sekunder.
7. Kontroller at en ny kjøring får ny kjørings-ID og at gammel ID står som `STALLED` eller `CANCELLED`.

Ingen database- eller miljøvariabelmigrering er nødvendig. Valgfrie `MANUAL_JOB_<STEG>_PROGRESS_TIMEOUT_SECONDS` kan overstyre standardfrister, men verdier under 60 sekunder aksepteres ikke.
