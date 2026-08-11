# Akseptanse – v19.22.0-rc16.26

## Omfang

Denne utgaven aktiverer kontrollert læring med terskel 63, uten å endre produksjonsportene for ordinære kjøp eller utføre virkelige handler.

## Verifisert lokalt

- Læringsscore er begrenset til intervallet 60–65 og anbefalt profil bruker 63.
- Læringsrisiko er begrenset til 75.
- Maksimalt tre nye læringsposisjoner per syklus og 15 000 i teoretisk posisjonsverdi.
- Gyldig markedspris og kritisk dataintegritet er obligatorisk.
- Manglende ikke-kritisk evidens blokkerer ikke alene en læringsposisjon.
- Paper-signaler brukes som teknisk læringsinput, mens Paper SELL kan avslutte læringsposisjoner.
- Produksjonsblokkere lagres separat, og produksjonskriteriene er uendret.
- Utfall måles etter 1, 5, 10, 20 og 60 observerte markedsdager.
- Målrettet testpakke: 22 bestått.
- Python-kompilering, ZIP-integritet og distribusjonsvalidering skal bestå før levering.

## Kjent regresjonsstatus

Full eldre testsamling har 39 eksisterende baselinefeil i v19.22.0-rc16.25. De samme eldre forventningsfeilene er fortsatt til stede. Ingen av dem tilhører den målrettede læringsflyten.

## Leveransestatus

`LOCAL_PASS_LIVE_REQUIRED`

Render/cron, databasepersistens og Pushover må bekreftes i produksjonsmiljøet etter utrulling. Ingen automatisk endring av produksjonsparametere er tillatt.
