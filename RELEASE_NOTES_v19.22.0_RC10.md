# Release notes v19.22.0 Investor Edition RC10

## Formaal

RC10 retter strukturen rundt evidenssok og diagnostikk. Versjonen endrer ikke `final_score`, rangering, produksjonsterskel, Autonomi-portefoljegrenser, Paper Trading-regler eller scheduler-tidene 08:00 og 22:00 Europe/Oslo.

## Endringer

- Ny kanonisk sokestatus skiller mellom:
  - `SEARCHED_RESULTS_FOUND`
  - `SEARCHED_NO_RESULTS`
  - `SEARCH_FAILED`
  - `NOT_SEARCHED_BUDGET`
  - `NOT_SEARCHED_DISABLED`
  - `NOT_SEARCHED_UNSUPPORTED`
  - `NOT_SEARCHED_POLICY`
  - `NOT_APPLICABLE`
- Eksisterende `status` og `coverage` beholdes som bakoverkompatible evidensfelt. Den nye sokestatusen brukes til diagnostikk og rapportforklaring, ikke til a endre handelsregler.
- Alle nye ikke-sok far maskinlesbar `reason_code`, blant annet `RANK_LIMIT`, `DATA_QUARANTINE`, `BUDGET_POLICY`, `MODULE_DISABLED`, `SOURCE_UNSUPPORTED`, `RATE_LIMITED` og `SOURCE_ERROR`.
- Kildebudsjett beregnes fra den faktiske sokeloggen. Lagrede tellere kan dermed kontrolleres mot planlagt, forsokt, vellykket, funn, ingen funn, feil og ikke-sok.
- Rapport-JSON far `evidence_search_summary` per kandidat og for hele kjøringen. Arkiverte rapporter normaliseres ved regenerering slik at kildebudsjettet bygges pa nytt fra den faktiske sokeloggen.
- PDF-ens kildedekningslogg viser en kompakt normalisert sokestatus og konkret arsak, feil eller kildeadresse uten a oke rapportlengden.
- Rapporter -> Drift har ny evidenssoksdiagnostikk med planlagt, forsokt, fullfort, treff, ikke sokt, feil og arsaksfordeling per kandidat.
- Ny audit `tools/audit_evidence_search_v19220_rc10.py` leverer JSON, CSV og Markdown uten a generere ny investeringsrapport.
- Auditen teller unikt etter kjøring + kandidat + evidensomrade + kilde, og blander ikke lenger alle interne `NOT_SEARCHED`-felt.
- `autonomous_trades.zip` kan brukes som historisk referanse for tidligere Autonomi-kjop, scorer, kjøringer og tidsperiode.

## Historisk funn i vedlagt materiale

De to rapportene fra 4. august inneholder 20 kandidater. Den detaljerte auditen fant 36 unike begrunnede ikke-sok, 1 unik sokefeil og 0 ukjente arsaker. De gamle rapportene har 32 avvik mellom lagret kildebudsjett og faktisk sokelogg; RC10 beregner disse tellerne fra loggen for nye kjøringer.

Historikkfilen inneholder 13 teoretiske Autonomi-kjop og 1 salg fordelt pa 5 kjøringer. Registrert kjopsscore er 73,3-81,0. Dette bekrefter at kjopskjeden tidligere har produsert BUY-resultater.

## Ikke endret

- Produksjonsterskel
- Beregning av investeringsscore og `final_score`
- Kandidatrangering
- Autonomis primare simulerte portefolje
- Paper Trading
- Innlogging og Husk meg
- Scheduler 08:00 og 22:00 Europe/Oslo
- Fail-closed produksjonshandel
