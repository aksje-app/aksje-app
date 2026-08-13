# Akseptanse – RC16.31e

Release kan godkjennes når alle punktene under er bekreftet.

1. Programmet viser `v19.22.0-rc16.31e` i grensesnitt og Pushover.
2. Faste rapporter vises som morgenrapport 08:00, ettermiddagsrapport 14:00 og kveldsrapport 22:00 i Europe/Oslo.
3. Kun én aktiv profil finnes for hver fast rapport.
4. En rapportkjøring oppretter PDF, lagringskvittering og høyst ett ordinært Pushover-varsel.
5. Kandidater lagres som læringsobservasjoner uten handler eller kapitalendring.
6. Samme kjøring kan repeteres uten duplikatobservasjon.
7. Observasjoner får målinger ved 5, 10, 20 og 60 markedsdager.
8. Simulerte salg er merket `production_applied=false`.
9. Hypoteser er skyggetester; produksjonspromotering avvises uten eksplisitt godkjenning.
10. Paper-skanneren har egen lås, eget heartbeat og oppdaterer siste vellykkede skann i et åpent markedsvindu.
11. Databaselagring viser ingen ukontrollert vekst fra rapporttestprofiler eller detaljerte læringsobservasjoner.

Live-punktene 4, 10 og 11 bekreftes etter deploy. Resten kontrolleres i releaseporten før ZIP opprettes.
