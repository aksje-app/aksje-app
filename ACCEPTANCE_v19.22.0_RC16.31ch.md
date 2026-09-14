# Akseptanse RC16.31ch

- [x] Modulnavn er «Jeep Commander 2.2».
- [x] 2025, 2026 og begge år samlet kan velges.
- [x] `2025/2026` klassifiseres som modellår 2026, ikke modellår 2025.
- [x] `2026/2027` klassifiseres som modellår 2027 og avvises fra 2025/2026-filteret.
- [x] 20 000 og 35 000 km kan velges; 35 001 avvises ved 35 000-grensen.
- [x] Fortaleza/Ceará, Nordøst-Brasil og hele Brasil kan velges manuelt.
- [x] 2.2 diesel kreves; eksplisitt 4x2 avvises.
- [x] Sort prioriteres uten å skjule et klart billigere alternativ i annen farge.
- [x] Kjøring har egen varig 15-minutters sperre og global lås.
- [x] Første vellykkede søk lager stille referanse.
- [x] Nye treff, prisfall og tydelig bedre tilbud oppdages.
- [x] Små prisvariasjoner under R$ 500 og 0,3 % behandles ikke som prisfall.
- [x] Mislykket Pushover beholdes for nytt forsøk.
- [x] Varslet har konkret kjøpsinformasjon og direkte lenke.
- [x] Doble treff innen samme kilde/søk dedupliseres.
- [x] Kildeblokkering og formatendring gir synlig feil, ikke null treff.
- [x] OLX-lignende HTML-kort uten JSON-data gir korrekt tittel, lenke, kilometer, pris, farge, sted og årpar.
- [x] Direkte OLX-søk avgrenses til Overland 2.2 TD 4x4 diesel.
- [x] Mobiauto brukes som tredje uavhengig markedsplass.
- [x] Avviste annonser grupperes etter konkret filterårsak i brukerflaten.
- [x] Konfigurasjon og treff ligger i et eget `temporary/jeep_commander_22`-område.
- [x] Manuell deaktivering, automatisk utløp og sletting av moduldata finnes.
- [x] Kontrollsenteret viser modulen under Marked og signaler.
- [x] Scheduler-status inkluderer bilmodulens tilstand.
- [x] Forrige varslingskontrakt er regresjonstestet.

## Testkvittering

- 41 relevante tester bestått.
- Python-kompilering bestått for alle endrede integrasjonsfiler.
- Fire eldre tester feiler identisk i originalgrunnlaget: to på manglende lokal `yfinance`, én på arbeidsmiljøets minnevern og én på en historisk kommentartekst. Ingen av dem skyldes RC16.31ch.
- Live parsing og faktisk Pushover må sluttkontrolleres etter deploy mot markedsplassenes gjeldende produksjonssider.
