# Fase 3 – godkjenningskrav før produksjon

## Faktiske funn
- 12 lagrede Autonomi-skanninger 12.–15.10.2026: 720 kandidatposter, ingen med `data_timestamp`. Dette dokumenterer manglende sporbarhet, **ikke** foreldede priser.
- Ny snapshot-diagnostikk: `UNKNOWN`, `VERIFIED`, `STALE`, opptelling og `review_required`. Syv kalenderdager er kun en diagnostisk terskel, ikke et krav for aksjekjøp.
- Gjeldende HOLD/WAIT er observasjonsnøytralt, ikke et teknisk BUY-signal; historiske kjøp med HOLD/WAIT er ikke dokumentasjon på at teknisk kjøpsbekreftelse ble gitt.

## Før strategiparametere endres
1. Sjekk CI Release gate og Superfond rotation validation mot siste commit.
2. Test at pris og kilde-tid samsvarer. Mangler kilde-tid, behold `UNKNOWN`; ikke erstatt med `captured_at`.
3. Logg andel `UNKNOWN` per marked og tidsvindu, uten ekstra dyre eksterne hentinger.
4. Beregn eventuelle gevinster/tap av alternative kjøpsfiltre i en **separat historisk test**, inkludert uteblitte vinnere, handler og transaksjonskostnader.
5. Følg samme regelsett for Autonomi, Superporteføljen og Superfond bare der datagrunnlag og instrumentslag gjør sammenligningen meningsfull.
6. Separat eksplisitt godkjenning før endringer i live kjøps-/salgsgrenser eller Render-deploy.

## Oppfølging
Release-pipeline er merget separat som PR 99 (commit `12b62cae46101894caf87550f99e93aaad67d28f`). PR 98 forblir en egen leveranse. Ingen strategiresultater er validert bare fordi CI er grønn.
