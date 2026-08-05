# AI Aksje Analyzer Pro v19.22.0 Investor Edition RC5

## Formål

RC5 retter valutavarslene uten å endre analysemodell, kandidatvalg, rapporttidspunkter eller handelsregler.

## Rettet

- Automatisk valutakontroll kjøres nå i den varige Render Cron-jobben hvert femte minutt, uavhengig av innlogging og markedstid.
- Manuell kurshenting, manuell grensekontroll og Pushover-test bruker samme autoritative kursinnhenting og samme lagrede status.
- Pushover-testen henter fersk kurs før utsendelse og viser kurs, grenser, status og kurstid.
- Helkjedetesten gjenoppretter ordinær kurs, runtime-status og heartbeat etter kunstig trigger.
- UI viser automatisk helse fra varig cron-heartbeat i stedet for en prosesslokal webtråd som er deaktivert på Render.
- Valutastatus er gjort responsiv på mobil; teknisk tabell og logg ligger lukket som standard.
- yfinance-innhenting har intradag-, fast_info- og download-fallback.

## Uendret

- `final_score`, kandidatrekkefølge og beslutningsregler.
- Morgenrapport kl. 08:00 og kveldsrapport kl. 22:00 Europe/Oslo.
- Produksjonshandel, Paper Trading og varslingsterskler.
