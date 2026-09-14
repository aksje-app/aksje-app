# RC16.31cm – sekvensielle markedsplassøk og valgfri deploylås

## Rettet

- DataForSEO Live mottar nå nøyaktig én oppgave per HTTP-kall.
- Webmotors og OLX kjøres sekvensielt og får uavhengig status, treff og feilmelding.
- Feil i den første markedsplassen hindrer ikke kontroll av den andre.
- Kostnadssperren vurderes på nytt før hvert enkelt API-kall.
- Faktisk antall utførte kall og rapportert kostnad summeres per svar.
- Fremdriften navngir markedsplassen og viser 1/2 og 2/2.

## Versjonsstyring

- `app_version.py` er fortsatt autoritativ versjonskilde for web og scheduler.
- `EXPECTED_APP_VERSION` er nå en valgfri nød-/deploylås.
- En gammel verdi blokkerer ikke en normal oppdatering.
- Sett `ENFORCE_EXPECTED_APP_VERSION=true` bare når en eksplisitt versjonslås ønskes.
- Kontroll av samme versjon og commit mellom web og scheduler er uendret og separat.

## Produksjonsgrense

Lokale tester kan bevise request-form, feilisolasjon og sikkerhetslogikk. Faktiske individuelle annonser hos begge markedsplasser må fortsatt bekreftes med den stille DataForSEO-testen etter deploy.
