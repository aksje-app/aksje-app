# Valideringsrapport RC16.31n

Status oppdateres først etter at alle lokale porter er kjørt.

## Golden replay

- Kilde: MI-20260815-080526.
- Autoritativ beholdning: `portfolio_after.json`.
- Åpne posisjoner: 12 i sammendrag og 12 detaljrader.
- Porteføljeverdi: 506103,44 simulerte kontoenheter.
- Kontanter: 281556,78.
- Investert andel: 44,37 %.
- Kontantandel: 55,63 %.
- Ledig kjøpslimit etter reserve: 230946,43.
- Avstemmingsdifferanse: -0,01 (avrunding).
- Generert PDF: 11 A4-sider; porteføljeside 1-2 visuelt kontrollert uten klipping.

## Lokale porter

- Python compileall: bestått.
- RC16.31n integritets- og låsetester samt relevante RC16.31l/m-regresjoner: 16/16 bestått.
- Full systemaudit: 0 feil og 0 advarsler.
- PDF-semantikk: alle avtalte porteføljefelt funnet i ferdig PDF.
- Visuell kontroll: porteføljeside 1 og 2 uten klipping eller tabelloverlapp.
- Full historisk unittest-discovery ble også kjørt. 165 tester passerte; 11 moduler krevde pytest som ikke er installert, og fire eldre tester har hardkodede versjons-/layoutforventninger som ikke representerer RC16.31n-kontrakten. Disse er ikke fremstilt som bestått.

## Distribusjon

- FULL: distribusjonsvalidering bestått.
- DELTA: distribusjonsvalidering bestått.
- Ingen runtime-data, hemmeligheter eller genererte rapporter finnes i pakkene.
- SHA-256 er kontrollert mot begge arkivene.

## Live

Render-verifikasjon er ikke utført og må gjennomføres etter deploy.
