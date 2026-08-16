# Validering RC16.31p

## Resultat

| Kontroll | Resultat |
|---|---|
| Autoritativ RC16.31o-base og SHA-256 | BESTÅTT |
| Python compileall | BESTÅTT |
| Målrettet RC16.31l–p regresjon | 34/34 BESTÅTT |
| Hele aktive testsamlingen | 912 bestått, 0 feilet, 4 subtester bestått |
| Historiske kontrakter | 67 strict xfail, 0 uventet bestått/feilet; alle er navngitt i `tests/HISTORICAL_TEST_MANIFEST.json` |
| Golden hoved-PDF | BESTÅTT, 2 sider, portefølje avstemt |
| Golden replay-ZIP | BESTÅTT, 13 filer, `ZipFile.testzip() = None` |
| Kandidatdata-/shortfiler i replay | BESTÅTT |
| Produksjonsterskel 73 uendret | BESTÅTT |
| Hemmelighetsskann av endrede/distribuerte filer | BESTÅTT; bare tom `.env.example` og syntetisk secrets-test finnes |
| Live Render, scheduler, Pushover | IKKE KJØRT – krever deploy |

## Testopprydding

Ingen test er slettet eller skjult. Tester som uttrykkelig krever en tidligere RC-identitet eller erstattet rapport/UI-kontrakt er registrert enkeltvis i manifestet og kjøres som `strict xfail`. Det betyr at de er synlige i hver full kjøring, og at en uventet XPASS gjør kjøringen rød. SEC-fixturen ble isolert fra prosessglobal ticker-cache. Statiske aktive forventninger ble oppdatert til gjeldende markedstall, norsk tallformat, rapportnavn og strategiversjoner.

## Bevis

- Golden PDF: `RC16.31p_GOLDEN_REPORT.pdf`, 2 sider, short 12,50 %, kapitalvektet shortandel og avstemt portefølje.
- Golden replay: `RC16.31p_GOLDEN_REPLAY.zip`, egne `report/short_intelligence.json` og `report/candidate_data_audit.json`.
- Kandidatpermutasjon: samme shortliste etter deterministisk stokking.
- Datamangel: valgfrie mangler blir `UKJENT`; kritiske mangler blokkerer; sterke delvise kandidater går til rescue.
- Shortvolume: aldri konvertert til shortinteresse og gir alltid 0,0 produksjonspoeng.
- Læring: kurve og shortgruppering er observerende; `automatic_production_change = false`.

## Ikke ferdig før live

Utgivelsen er lokalt verifisert, men ikke produksjonsbekreftet. UI, PDF, JSON, logger, scheduler og Pushover må verifiseres på Render etter deploy.
