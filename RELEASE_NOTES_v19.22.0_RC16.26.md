# v19.22.0-rc16.26 – Controlled Learning Activation

Denne versjonen aktiverer kontrollert læring med simulerte penger uten å svekke Autonomis produksjonsport.

## Endret

- Læringsscore er satt til 63 og kan bare konfigureres innenfor 60–65.
- Maksimal risiko for læringskontoen er 75; produksjonsgrensen er fortsatt uendret.
- Maks tre nye læringskjøp per syklus og maksimalt 15 000 per simulert posisjon.
- Gyldig markedspris, beslutningsgyldige markedsdata og bestått kritisk integritetskontroll er fortsatt obligatorisk.
- Manglende ikke-kritisk evidens registreres, men blokkerer ikke alene et læringskjøp.
- Ferske Paper-signaler brukes som teknisk læringsinput, men kan aldri autorisere produksjonsordre.
- Hvert læringskjøp lagrer hvorfor produksjonsporten avviste samme kandidat.
- Resultater måles etter 1, 5, 10, 20 og 60 observerte markedsdager.
- Læringsposisjoner følges opp med stop-loss, trailing stop, gevinstmål, scorefall, Paper-salgssignal og maksimal læringshorisont.
- En posisjon som selges kan ikke kjøpes tilbake i samme syklus.

## Uendret sikkerhetsgrense

- Ingen ekte handler er aktivert.
- `autonomy_main` og produksjonsportens score-, evidens-, data-, risiko- og ordrekrav er uendret.
- Læringskontoen har separat kapital, posisjoner, ordrer og resultatmåling.
- Læring kan ikke automatisk endre produksjonsparametre.
