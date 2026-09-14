# Akseptanse RC16.31cl

## Bilmodul

- [x] Fremdriftslinje viser prosent og aktiv fase for DataForSEO-test.
- [x] Fremdriftslinje viser prosent og aktiv fase for komplett manuelt søk.
- [x] Direkte kilder, DataForSEO, filtrering, rangering og varslingskontroll har egne fremdriftstrinn.
- [x] Test- og søkeknapp er deaktivert mens jobben kjører.
- [x] API, OLX, Webmotors og «0 Pushover» har permanente grønne/røde statusbokser.
- [x] Null individuelle treff skilles fra «ikke testet» og teknisk API-feil.
- [x] Testtidspunkt, individuelle lenker, komplette kandidater og estimert kostnad vises.
- [x] Aktiv, Pauset og Stoppet er separate driftsmoduser.
- [x] Direkte knapper aktiverer, pauser eller stopper uten å slette historikk.
- [x] Pause stanser automatiske søk; manuelt søk er fortsatt mulig.
- [x] Stoppet blokkerer automatiske og manuelle søk samt varsler.
- [x] Modulstatus kontrolleres mellom direkte kilder, slik at ekstern stopp kan avslutte resten av jobben.
- [x] Standard nattpause er 01:00–06:00 Fortaleza-tid.
- [x] Nattpausen kan slås av eller få andre klokkeslett.
- [x] Manuelt søk omgår nattpausen, men ikke full stopp.
- [x] Cron-kall i nattpausen bruker ingen bilkilde eller DataForSEO.
- [x] Første planlagte søk etter nattpausen blir ikke forsinket av nattlige cron-oppvåkninger.

## Aksjer og øvrige bakgrunnsjobber

- [x] Ordinær paper-skanning henter bare åpne aktiverte markeder.
- [x] Fresh Trend følger samme markedskalender før kostbar kandidatoppdatering.
- [x] Helg og helligdag gir ingen automatisk kandidatoppdatering.
- [x] Norge, Sverige og USA vurderes separat med egne tidssoner og sommertid.
- [x] Når ett marked er åpent, behandles bare kandidater fra åpne markeder.
- [x] Neste reelle markedsåpning beregnes og lagres.
- [x] Hoppede lukkede kontroller og sparte kandidatoppdateringer telles.
- [x] System/admin viser markedsstatus, lokal tid, neste åpning og besparelse.
- [x] Valutavarsler kjører før aksjeskannergaten og stoppes ikke av markedshvile.
- [x] Rapportplanlegger og vedlikehold er uavhengige av markedshvilen.

## Testkvittering

- [x] Samlet målrettet suite: 65/65 bestått.
- [x] Python-kompilering: ni endrede/importerende runtimefiler bestått.
- [x] Tidligere scanner-regresjoner kjørt med avtalt tre-markedsprofil.
- [ ] Virkelig DataForSEO-test gir individuelle OLX-treff etter deploy.
- [ ] Virkelig DataForSEO-test gir individuelle Webmotors-treff etter deploy.
- [ ] Første produksjonskjøring viser fremdrift og null Pushover under baseline.
