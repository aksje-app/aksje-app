# Valideringsrapport RC16.31aq

## Resultat

- Full lokal regresjon: 1042 bestått, 4 deltester bestått og 0 feil.
- Aktiv xfail-gjeld: 0.
- Historiske, eksplisitt deselecterte kontrakter: 65.
- Gjeldende erstatningskontrakter: 6 nye, 15/15 sammen med AQ-anbefalingstestene.
- Målrettet rapport-/PDF-regresjon: 29 bestått, 3 forventede xfail og 0 feil.
- Python: 3.12.13. Låste avhengigheter: 70 av 70 verifisert.
- Streng produksjonsterskel: 73,0. Maksimal risiko: 65,0.
- Moderate anbefalinger kan ligge 0–6 poeng under streng terskel; ingen transaksjonsfullmakt.

## Ende-til-ende-replay

Den faktiske tidligere problemkjøringen med 64 kandidater ble spilt gjennom den
kanoniske beslutnings- og rapportkjeden.

- Strenge kjøpskandidater: 0.
- Moderate kjøpsanbefalinger: 8.
- Norge: 5. Sverige: 1. USA: 2.
- Tickers: BMY, WAWI.OL, GOOGL, AKER.OL, SSAB-A.ST, SATS.OL, AKSO.OL, PEXIP.OL.
- Handelsautoriserte moderate anbefalinger: 0.
- Rapportintegritet: bestått.
- Rapportdokument: 8 anbefalinger.
- Hoved-PDF: 3 sider, alle 8 anbefalinger synlige, semantisk kontroll bestått.
- Teknisk PDF: 11 sider, alle 8 anbefalinger synlige, semantisk kontroll bestått.
- Null-anbefalingsrekke etter replay: 0.
- Rapport-ZIP: konsistenskontroll bestått, `candidate_scores.json` inkludert.
- Scorekontrakt: 60 analyserte, 4 portefølje-only, 0 manglende scorer.

## Sikkerhetsporter

Ugyldige markedsdata, risiko over 65, eksisterende posisjon, kildefeil,
kildekonflikt, kritisk negativt signal eller teknisk ventestatus kan ikke få
moderat kjøpsanbefaling. `production_buy_authorization` avviser alltid moderate
anbefalinger. Programmet utfører ingen virkelige transaksjoner.

## Faste kjøringer

- Morgen 08:00, ettermiddag 14:00 og kveld 22:00 Europe/Oslo.
- 14:00-kjøringen setter force refresh og omgår normal seks-timerscache.
- Formålet er å finne nye opplysninger etter 08:00 før nordiske børser stenger.
- Målrettet scheduler-/rapportkontroll: 41 bestått og 0 feil.
