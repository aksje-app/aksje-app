# Akseptanse v19.22.0 Investor Edition RC10

Versjonen kan ikke produksjonsgodkjennes for live Render for alle punktene er dokumentert.

## Ren deploy

- Programmet viser `v19.22.0-rc10`.
- RC10 FULL er deployet som samlet kode, ikke blandet med eldre `app.py` eller evidensmoduler.
- Runtime-data og hemmeligheter ligger ikke i repository.

## Evidenssok

- Hver kildepost har `search_status` og `reason_code`.
- Ingen ny post bruker ren `NOT_SEARCHED` som kanonisk sokestatus.
- `SEARCHED_NO_RESULTS` vises som fullfort kontroll uten funn, ikke som kildefeil.
- Rate limit, kvote og teknisk feil vises som `SEARCH_FAILED` med konkret arsaks-/feilkode.
- Budsjettstyrt hopp vises som `NOT_SEARCHED_BUDGET`.
- Rang-/prioriteringsbegrensning vises som `NOT_SEARCHED_POLICY` med `RANK_LIMIT`.
- Datakarantene vises med `DATA_QUARANTINE`.

## Kildebudsjett og audit

- Ny rapport-JSON inneholder `evidence_search_summary`.
- `source_budget.planned` samsvarer med antall poster i sokeloggen.
- `attempted`, `successful`, `with_facts`, `no_events`, `failed` og `not_searched` samsvarer med loggen.
- RC10-auditen viser `unknown_reason_records = 0` for en ny live kjøring.
- RC10-auditen viser `budget_issue_count = 0` for en ny live kjøring.
- Unike mangler telles etter kjøring + kandidat + omrade + kilde.
- JSON-, CSV- og Markdown-resultatene viser samme antall.

## Historisk kjopsreferanse

- `autonomous_trades.zip` lastes og viser 13 BUY, 1 SELL og 5 kjøringer.
- Historisk kjopsscore vises uten a endre dagens terskel.
- Autonomi og Paper Trading omtales separat.

## Rapport og UI

- Kandidatens kildedekningslogg viser normalisert sokestatus og konkret arsak, feil eller kildeadresse.
- Rapporter -> Drift viser samme sokestatus, budsjett og arsaksfordeling som rapport-JSON.
- Ingen tekst overlapper eller klippes i PDF.
- Top 1-3 forblir pa side 1.
- Rapportknapper forblir pa Rapporter etter rerun.
- Banner testes i alle fire kombinasjoner fra RC9-akseptansen.

## Beskyttede funksjoner

- `final_score`, kandidatvalg og rangering er uendret.
- Produksjonsterskel og handelsregler er uendret.
- Autonomis primare simulerte portefolje og Paper Trading er separate.
- Scheduler kjører 08:00 og 22:00 Europe/Oslo.
- Produksjonshandel forblir fail-closed.
