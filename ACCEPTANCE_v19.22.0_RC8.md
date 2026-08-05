# Akseptansekrav v19.22.0 RC8

RC8 kan ikke produksjonsgodkjennes før følgende er bekreftet på Render:

1. Ekstra banner kan slås av/på gjentatte ganger uten hvitt tomrom, gamle grafer eller økt sidelengde.
2. Manuell oppdatering beholder aktiv side og viser bare én arbeidsflate.
3. Visningstidssone lagres og viser riktig tid i Europe/Oslo, Europe/Lisbon og minst én brasiliansk tidssone.
4. Scheduler fortsetter på 08:00 og 22:00 Europe/Oslo uavhengig av visningstidssone.
5. Valutakurs, grensestatus og Pushover viser samme ferske kurs og kurstid, med to desimaler.
6. Valutavarsler har ingen tekstoverlapping eller horisontal overflyt på mobil og desktop.
7. Top 1-3, final_score og beslutning samsvarer mellom UI, JSON og PDF.
8. Alle PDF-sider kontrolleres visuelt etter en ny live rapport.
9. Innlogging, Husk meg, refresh og utlogging verifiseres uten regresjon.
