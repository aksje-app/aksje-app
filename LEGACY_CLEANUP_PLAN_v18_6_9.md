# Legacy Cleanup Plan v18.6.9

Denne runden skjuler og samler gamle innganger, men sletter ikke store kodeblokker.
Grunnen er enkel: vi skal rydde uten aa miste fungerende eksport, rapporter,
Paper Trading, AI Kandidattest eller kildedata.

## Backup-prinsipp

- Det lages bare en ny changed_files_only.zip i denne runden.
- Forrige zip, v18.6.8, er fallback dersom noe maa rulles tilbake.
- Ekstra backup-zip lages ikke naa, fordi arbeidsregelen er en ny versjon og en zip per GO.

## Det som er samlet i UI

- Marked er hovedinngang for Rangering, Heatmap, Markedsklima, Lagrede signaler, IPO, Regime, Makro og Nyheter.
- Varsler og watchlist er hovedinngang for Varselsenter, Watchlist/signaler og Valutavarsler.
- Services skjules fra normal brukerflate og beholdes bare som teknisk kontroll/fallback.

## Kandidater for senere sletting

1. Inaktive kontrollsenter-varianter i workspace_layout.py.
2. Eldre duplikatdefinisjoner av valutavarsel-panelet i app.py.
3. Gamle standalone-panelinnganger for Markedsklima, IPO, Nyheter, Marked/rangering, Watchlist og Valutavarsler.
4. Gammel Test 1-10-arbeidsflyt-kode som ikke lenger brukes etter at AI Kandidattest ble hovedmotor.

## Krav foer sletting

- Full pytest maa passere.
- AI Kandidattest maa kunne kjore, eksportere CSV/JSON/HTML og vise detaljrapport.
- Marked -> Rangering, Heatmap, Markedsklima, Lagrede signaler, IPO, Regime, Makro og Nyheter maa kunne aapnes.
- Varsler og watchlist maa vise lagrede varsler, watchlist og valutavarsler.
- Paper Trading og kontroll maa vise beholdning, handelslogg, kontrollkort og rapport/varsling.

## Anbefalt cleanup-runde

Neste cleanup-runde bor kun rydde en kategori av gangen:

1. Fjern inaktive kontrollsenter-varianter.
2. Kjor full pytest og en kort web-smoke.
3. Fjern duplikat-valutavarsel-definisjoner.
4. Kjor full pytest og valuta/Pushover-smoke.
5. Fjern gammel workflow-kode bare hvis AI Kandidattest/Paper Trading dekker samme brukerflyt.
