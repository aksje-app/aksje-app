# Akseptanse RC16.31cm

- [x] Ett DataForSEO Live-kall inneholder nøyaktig én task.
- [x] Webmotors og OLX bruker to separate, sekvensielle kall.
- [x] Feil i Webmotors hindrer ikke OLX-kallet.
- [x] Hver markedsplass beholder egen status og feilmelding.
- [x] Kostnadssperre kontrolleres før hvert kall.
- [x] Antall kall og kostnad summeres fra faktisk utførte svar.
- [x] Stille validering krever fremdeles minst én individuell OLX- og Webmotors-lenke.
- [x] DataForSEO kan fremdeles ikke aktiveres før begge er grønne.
- [x] `app_version.py` er autoritativ normalversjon.
- [x] Gammel `EXPECTED_APP_VERSION` blokkerer ikke normal deploy.
- [x] Eksplisitt `ENFORCE_EXPECTED_APP_VERSION=true` gjør mismatch blokkerende.
- [x] Web/scheduler-kontroll av versjon og commit er fortsatt uavhengig og blokkerende.
- [x] 25/25 målrettede tester bestått.
- [x] Python-kompilering bestått for alle berørte runtimefiler.
- [ ] Faktisk OLX-resultat grønt etter deploy.
- [ ] Faktisk Webmotors-resultat grønt etter deploy.

Merk: To eldre, ikke-relaterte rapportteksttester ble også observert som røde i bredere utvalg. De gjelder historiske tekstetiketter og er ikke endret eller skjult i denne leveransen.
