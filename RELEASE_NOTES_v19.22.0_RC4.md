# AI Aksje Analyzer Pro v19.22.0 Investor Edition RC4

Dato: 2026-08-04

## Formål
RC4 styrker rapportintegritet og retter de konkrete live-avvikene som ble påvist etter RC3 uten å endre final_score, kandidatvalg, handelsregler, scheduler-tidene eller produksjonsportene.

## Rettet
- Rapportsenteret følger rekkefølgen status, handlinger, siste rapporter, historikk og avanserte innstillinger.
- Leverings- og varslingsvalg er samlet i adskilte, luftige kort.
- Manuelle rapportjobber kjøres i bakgrunnen med varig status og fremdriftslinje.
- Morgen-, kveld-, natt-, utkast- og innhentingsjobber bruker samme bakgrunnsstatus.
- Menyklikk blir autoritativt navigasjonsvalg; hoved- og reserve-sidebaren er synkronisert.
- Scheduler-kontroll i UI er strupet og helsesjekken skriver ikke til lagring ved hver rerun.
- «Husk meg» er gjeninnført med tilfeldig, tidsbegrenset og tilbakekallbart token. Passord eller token legges ikke i URL eller localStorage.
- Top 1–3, fire separate kvalitetsmål, hovedkonklusjon og sporbarhet ligger på PDF-side 1.
- Synlig samlet pålitelighetsscore er fjernet.
- «Kontrollert – ingen hendelser» gir ikke evidensstraff eller kildefeil.
- ASCII-konfidenslinjer er fjernet, læringsaktivitet er omtalt som simulert læringsposisjon, og kandidatseksjoner har tydelig tickerkontekst.
- Full SHA-256, separat analyse-ID og erstattet rapport-ID vises i rapporten.

## Uendret
- final_score og scoreformel.
- Kandidatrekkefølge og kandidatvalg.
- Produksjonsterskel og handelsregler.
- Morgenrapport 08:00 og kveldsrapport 22:00 Europe/Oslo.
- Fail-closed produksjonshandel og Paper Trading-regler.

## Status
Lokal validering er bestått: 636 tester og 4 deltester, Python-kompilering, full systemaudit, JSON/PDF-sammenligning, visuell kontroll av 13 PDF-sider og distribusjonskontroll av FULL og DELTA. RC4 kan likevel ikke erklæres produksjonsklar før faktisk Render-test av innlogging, navigasjon, ytelse, rapportkjøring, scheduler og Pushover er gjennomført.
