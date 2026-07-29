# Testrapport v19.14.1

Dato: 2026-07-28

## Automatiske tester

- Pytest: 490 bestått, 0 feilet, 4 deltester bestått.
- Separat regresjonsrunner: 362 bestått, 0 feilet.

## Målrettede integritetstester

Testene dekker:

- kjøp bare ved Kjøpskandidat + BUY + gyldige data/evidens
- blokkering av REVIEW/Overvåkes automatisk
- blokkering av kjøp og salg av samme ticker
- rollback av ordinære handler
- rapportblokkering av AAPL-feilen fra v19.14.0
- versjonssynkronisering
- kjernemarkeder i Enkel-modus
- prioritert vurderingsrekkefølge 1–3
- entydig produksjonsterskel
- komprimering av nestede råkopier
- svenske FI- og Nasdaq-parserne
- direkte offisiell kildekontroll før sekundær oppdagelse
- norsk rapporttekst og fjerning av foreldet oppfølgingsfelt

## Funksjonell kontroll mot live-datagrunnlag fra v19.14.0

- Den opprinnelige rapporten ble korrekt avvist med fem integritetsfeil knyttet til AAPL-kjøp/salg.
- Korrigert kanonisk rapport bestod integritetskontrollen.
- Produksjonsterskel: 73,0.
- Kjøpskvalifiserte kandidater: 0.
- Kontroll-JSON redusert fra 13 564 876 til 5 594 187 byte, 58,76 %.
- PDF: 11 sider.

## Visuell PDF-kontroll

Alle 11 sider ble rendret ved 170 DPI og kontrollert for:

- lesbarhet og sideskift
- tabelloverlapping
- prioritert 1–3-rangering
- fravær av medaljer
- fravær av brukerrettede `REVIEW`, `NOT_SEARCHED`, `partial source failure` og rå portnavn
- samsvar mellom produksjonskjøp, kandidater og beslutningstrakt

Ingen kjent visuell blokkeringsfeil ble funnet.
