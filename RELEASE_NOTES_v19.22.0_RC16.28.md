# v19.22.0-rc16.28 – Verifiable Learning Runtime

## Hovedendringer

- Nye rapportjobber bruker Norge, Sverige og USA med 25 symboler per marked som avgrenset standard.
- Lagrede faste jobber beholder operatorens markeder, skanneantall og analysebudsjett. De blir ikke lenger tvangsmigrert ved innlasting.
- Jobbprofilene kan fortsatt redigeres og endringene gjelder bare fremtidige kjøringer.
- 30-minutters akseptansemodus kjører den faktiske Autonomi-motoren og den kontrollerte læringskjeden.
- Akseptansetesten kan bare opprette isolerte `LEARNING_ONLY`-observasjoner. Ordinære produksjonsporter og ekte handel er uendret og fail-closed.
- Hver læringskjøring får et varig `PASS`, `PARTIAL` eller `FAIL`-bevis med konkrete blokkoder.
- `PASS` krever at en teoretisk læringsobservasjon er lagret. `PARTIAL` betyr at kjeden og blokkdiagnostikken virker, men at ingen kandidat kvalifiserte.
- Pushover-testen viser læringsresultat, beslutningsantall og læringshandler.
- Diagnosepakken inneholder avgrenset læringsprofil, scheduler-heartbeat, teststatus, posisjonssammendrag, ytelse, beslutninger, handler, blokkoder og SHA-256.
- Komplett rapport- og læringsarkiv tar med siste læringsakseptanse og blokkfordeling.

## Sikkerhet

- Ingen API-nøkler, tokens, passord eller miljøverdier tas med i diagnosepakken.
- Ingen produksjonsterskel er senket.
- Ingen meglerhandel er innført.
- Læringsnotional er fortsatt 15 000 og læringsterskelen fortsatt 63 i den separate teoretiske læringskontoen.

Status: `LOCAL_PASS_LIVE_REQUIRED`.
