# Akseptanse v19.22.0-rc16.31

RC16.31 retter den reproduksjonsbekreftede RC16.30-feilen fra
`MI-20260809-114617` og `MI-20260809-130539`.

## Obligatoriske porter

1. Null/manglende numeriske porteføljefelt gir forklart blokkering, aldri TypeError.
2. Eksakt `MARKET_SCAN`-callback med manglende tellere kan ikke gi `max(1, None)`.
3. Autonomifeil eksporterer stage, feiltype og traceback.
4. `run_id` bevares også når sluttkontrakten feiler.
5. Pushover blokkeres når pre-notification-audit feiler, bortsett fra en validert fast rapport der eneste feil er `THEORETICAL_DECISIONS`; denne må merkes som begrenset og ikke beslutningsklar.
6. `COMPLETE` og alle grønne steg publiseres først etter 13/13 godkjente steg.
7. Full livekjøring på Stabilisering ender `COMPLETED`.
8. En ticker kan ikke ha terminal `SKIP` og ferdig `BUY` i samme læringsresultat.
9. Rapportpakken inneholder `portfolio_snapshot.json`, og beslutningsreplay gir `COMPLETED` med én rad per kandidat.
10. En ny autonomikjøring produserer og lagrer et kontrollert `FULL_REPLAY`-snapshot.
11. JSON, TXT og PDF har identiske læringshandler, antall og priser.
12. PDF viser rapportvarsling og læringsvarsling som separate kanaler.
13. PDF viser alle ferdige læringshandler og produksjonsblokkeringene deres.
14. Alle PDF-sider renderer uten klipping, overlapp, svarte felt eller manglende sidetopp/-bunn.
15. Resultatfeltenes tekster er uendret; tall bruker kompakt sats og norsk desimalformat.
16. Automatisk rapporttest bruker stabil serie-ID og sender tydelig 1/4–4/4 uten sekunddrift.
17. Manuell test er eksplisitt separat og endrer ikke automatisk suksessteller.
18. Bare faktisk sendt Pushover øker automatisk suksessteller.
19. Fire simulerte cronstarter ender terminalt med fire beståtte tester og ett sluttvarsel.
20. Midlertidig databasefeil prøves på nytt; permanent lagringsfeil maskerer ikke rapportfeilen.
21. Rapportsenteret viser serie-ID, neste forsøk og testtidslinje.
22. Rask systemkontroll berører ikke markedsskann, portefølje eller læringshandlinger.
23. Diagnosepakken inneholder testtidslinje, systemkontroll og Pushover-audit med SHA-256-manifest.
24. Kandidatregnskapet avstemmes hardt: kjøp + overvåking + manuell vurdering + avvist = totalt antall kandidater.
25. Analytisk kjøpssignal, kjøpsgodkjenning og gjennomførbar handel vises som tre separate mål.
26. Norsk desimalformat brukes konsekvent i investor-PDF og tekstversjon uten å endre datoer, versjoner, ID-er eller URL-er.
27. Interne historikkoder, engelske tekniske seksjonstitler, dupliserte jobbnavn og maskinlesbare integritetslinjer vises ikke i investorrapporten.
28. Referanserapporten er komprimert fra 7 til 6 A4-sider, og alle seks sidene er visuelt kontrollert.
29. PDF-semantikk må stemme med kanonisk JSON og den komplette kandidatavstemmingen før eksport godkjennes.
30. Rapport-, testserie-, terminal- og læringsvarsler viser programversjonen fra den sentrale versjonskontrakten.
31. Jobbnavn dedupliseres i både testjobb, Pushover og PDF.
32. Læringsvarsel bruker norsk desimalformat og mellomrom før prosenttegn.
33. Automatisk varsel viser deltest og kjøringsforsøk som separate størrelser og forklarer at forsøk inkluderer retry.
34. Rapportsenteret viser eksplisitt 0/4-fase, statusforklaring og forventet resultat mens fullkjeden kjører.
35. Rapportvarsel viser rapport-ID, lokal rapporttid og kort status for markedsdata/evidens.
36. En validert og lagret fast rapport med kun `THEORETICAL_DECISIONS`-feil sendes med tydelig begrensningsvarsel.
37. Automatisk rapporttest forblir fail-closed ved samme feil og øker ikke suksesstelleren.
38. Feil i én fast rapportjobb hindrer ikke neste forfalte jobb i samme scheduler-syklus.
39. Schedulerstatus viser vellykkede og feilede jobber separat med feil per jobb.
40. Tre stabile produksjonsjobber finnes og er aktive kl. 08:00, 14:00 og 22:00 Europe/Oslo på hverdager.
41. Kanonisk resultat bruker atomisk opprett-eller-les og tåler to midlertidige databasefeil før tredje forsøk lykkes.
42. Resultatindeksfeil kan ikke ugyldiggjøre et allerede lagret uforanderlig resultat.
43. Morgen-, ettermiddags- og kveldsrapport forsøkes i kronologisk rekkefølge, og én injisert jobbfeil stopper ikke de andre.
44. Leveringsretry bruker lagret kjøring og starter ikke markedsskann, Autonomi eller læring på nytt.
45. Dagens leveranseregnskap viser PDF, lagring, Pushover, rapport-ID og status for alle tre rapportene.
46. En rapport som mangler 30 minutter etter planlagt tid utløser høyst ett uavhengig driftsvarsel per dato og jobb.
47. Automatisk rapporttest bruker alltid `MI-AUTONOMY-REPORT-TEST` og kan ikke oppfylle eller forurense obligatorisk leveringsregnskap.
48. Kjente eldre faste dublettprofiler deaktiveres, mens egendefinerte jobbprofiler beholdes uendret.
49. Et eldre fast tidspunkt 16:30 migreres til 14:00; obligatorisk ettermiddagsrapport beregnes som 14:00 Europe/Oslo også gjennom sommertid.
50. Planlagt tidspunkt i Pushover vises som lokal Europe/Oslo-tid, ikke rå UTC.
51. Paper-toppstatus bruker varig scanner-heartbeat og varsler eksplisitt når scannen er foreldet.

Status: målrettede rapport- og integritetstester er bestått. Faktisk 1/4–4/4 i Render er siste driftsakseptanse etter deploy.
