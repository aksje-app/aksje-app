# Deploy v19.22.0-rc16.31

Installer kun på Stabilisering først.

1. Last opp FULL-pakken.
2. Bekreft `v19.22.0-rc16.31`.
3. Start én manuell fullkjede.
4. Bekreft 13/13 steg, PDF og terminal `COMPLETED`.
5. Bekreft Pushover bare etter bestått Autonomi-audit.
6. Last ned diagnose- og rapportpakke før eventuell ny kjøring.
7. Åpne den nye PDF-en og bekreft at kandidatavstemmingen nederst viser samme total på begge sider av «avstemt».
8. Bekreft at testserien sender 1/4, 2/4, 3/4 og 4/4 som fire separate varsler.
9. Bekreft at hvert rapportvarsel viser `Programversjon: v19.22.0-rc16.31`, rapport-ID og datastatus.
10. Bekreft at læringsvarselet viser norsk prosentformat, eksempelvis `0,12 %`.
11. Bekreft at en fast rapport med kun teoretisk beslutningsfeil mottas som «BEGRENSET RAPPORT – IKKE BESLUTNINGSKLAR» med fungerende rapportlenke.
12. Bekreft at en feilet fast jobb ikke hindrer neste forfalte jobb, og at schedulerstatus viser både vellykkede og feilede jobber.
13. Bekreft tre aktive obligatoriske profiler: 08:00, 14:00 og 22:00 Europe/Oslo.
14. Kontroller dagens leveranseregnskap etter hver kjøring: PDF, lagring, Pushover og rapport-ID skal være bekreftet.
15. Injiser bare i Stabilisering én midlertidig lagringsfeil og bekreft at samme rapport-ID fullføres uten ny markedsskanning.
16. Bekreft at manglende rapport gir ett driftsvarsel etter 30 minutter og ikke dupliseres i senere cron-sykluser.
17. Bekreft at eldre fast 16:30-/dagsrapport er deaktivert og ikke lager dublett etter 14:00-rapporten.
18. Bekreft at testvarsler viser `Jobb: Autonomi rapporttest` og aldri navnet til en obligatorisk produksjonsrapport.
19. Bekreft at Pushover viser planlagt tid i Europe/Oslo, og at 14:00-rapportens lagrede UTC-slot følger sommer-/vintertid korrekt.
20. Sammenlign Paper-toppens scan-tid med scannerstatus og siste automatiske Paper-handel; en foreldet heartbeat skal vises som `SCAN FORELDET`.
