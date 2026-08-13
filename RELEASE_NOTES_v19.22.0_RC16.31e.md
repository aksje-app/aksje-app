# RC16.31e – observerbar og kontrollert Autonomi-læring

RC16.31e gjør læringsmotoren målbar uten å senke sikkerhetskravene for den ordinære Autonomi-porteføljen.

## Endringer

- Alle vurderte kandidater lagres som isolerte læringsobservasjoner.
- Utfall måles etter 5, 10, 20 og 60 unike markedsdager.
- Stop-loss, take-profit og trailing-stop simuleres i skyggeobservasjonene.
- Modnede, avviste kandidater kan opprette en begrenset hypotese for skyggetest.
- Ingen observasjon, hypotese eller test kan handle, reservere kapital eller endre produksjonsparametere.
- Produksjonspromotering krever fortsatt uttrykkelig brukergodkjenning.
- Læringsvarsler sendes ved endring og ellers maksimalt som ukentlig status.
- Rapporten klokken 14:00 heter konsekvent «Ettermiddagsrapport».
- Den faktiske kjøpslisten heter «Kjøpsgodkjente kandidater» og er adskilt fra vurderingsrekkefølgen.
- Detaljerte læringsobservasjoner er begrenset til 2 000 rader og beskyttes av lagringsoppryddingen.

## Uendret sikkerhetsmodell

Ordinære kjøps-, salgs-, risiko-, evidens- og datakvalitetskrav er ikke redusert. Paper Trading og Autonomi har fortsatt separate porteføljer, og læringsobservasjoner er kun skyggeberegninger.
