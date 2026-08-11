# Deploy – v19.22.0 RC16

## Anbefalt deploy

Bruk RC16 FULL som samlet erstatning over RC15. Behold eksisterende persistent disk og PostgreSQL.

Render-startkommando:

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 10000
```

Python: 3.11.9. Kravfilen beholder `streamlit==1.57.0` og `starlette==1.3.1`.

## Første live-kontroll

- Bekreft versjon `v19.22.0-rc16`.
- Åpne Rapporter og start én rapport. Ikke start flere parallelle kjøringer.
- Bekreft automatisk fremdrift uten manuell nettleseroppdatering og uten nedtonet fullside.
- Bekreft at sidemenyen beholder samme bredde, knappehøyde og typografi etter full lasting.
- Kontroller beslutningssporet for alle Top 10: enten BUY eller én konkret første blocker.
- Last ned komplett rapportpakke og kontroller identitet mellom PDF, TXT, JSON, snapshots og manifest.
- Bekreft at PDF-lenken inneholder samme rapport-ID som rapporten og ikke endres når en senere rapport genereres.
- Start komplett rapport- og læringsarkiv under Rapporter → Drift; bekreft worker-heartbeat, fremdrift og nedlasting.
- Kontroller at replayeksporten viser antall funn, dubletter, full/delvis replay og manglende historikk.
- Aktiver anbefalt læringsprofil bare etter kontroll: 500 000 referanseportefølje, 15 000 LEARNING_ONLY-notional, maks tre nye læringsposisjoner per kjøring.
- Kontroller scheduler 08:00/22:00 og Pushover mot samme rapport-ID.

Ingen produksjonsklar-erklæring gis før live-kontrollen er dokumentert.
