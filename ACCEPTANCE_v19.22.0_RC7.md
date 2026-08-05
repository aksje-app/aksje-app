# Akseptansekrav v19.22.0 RC7

RC7 kan ikke produksjonsgodkjennes foer foelgende er bekreftet paa Render:

1. Bare én hovedarbeidsflate rendres per kjøring.
2. Autonomi -> Rapporter viser ikke en ny Autonomi/Rapporter-kopi nederst paa siden.
3. Manuell nettleseroppdatering gjenoppretter samme hovedgruppe, panel og indre fane.
4. Fem gjentatte oppdateringer paa Rapporter gir samme resultat uten feilruting.
5. Oversikt <-> Rapporter bytter korrekt begge veier.
6. Alle Autonomi-arbeidsflater beholder riktig fane etter widget-rerun.
7. Valutavarsler forblir aktiv etter alle handlinger fra RC6.
8. Paper Trading beholder valgt fane etter handling og refresh.
9. Analyse, Top Picks, Long Engine og System beholder riktig panel etter refresh.
10. URL-en veksler ikke kontinuerlig mellom `control_center` og en panelspesifikk rute.
11. Programmet gaar ikke inn i en rerun-loop og blir ikke gradvis tregere ved normal navigasjon.
12. Mobil og desktop har samme rute- og refresh-resultat.
13. Innlogging, Husk meg, scheduler, Pushover og rapportlevering fungerer uendret.
