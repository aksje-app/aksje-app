# v19.22.0 Investor Edition RC2

## Formål
Denne release candidate stabiliserer validerings- og leveransegrunnlaget for Investor Edition etter RC1.

## Endringer
- Foreldede tester som hardkodet v19.17-versjoner følger nå den kanoniske appversjonen.
- Ekstern testfixture under `/mnt/data` er erstattet med deterministiske testdata i testpakken.
- Releaseaudit og statisk sikkerhetsaudit følger aktiv appversjon og aktive releasedokumenter.
- RC2 har komplett release-, deploy- og akseptansdokumentasjon.
- DELTA-generatoren er sikret slik at runtime-data, cache og lokale hemmeligheter aldri kan havne i `DELETE_FILES.txt`.
- Rapportintegritet, versjonssporbarhet og Investor Edition-merking verifiseres lokalt.

## Ikke endret
- `final_score` og kandidatvalg.
- Handelsregler eller produksjonsterskler.
- Scheduler-tidene 08:00 og 22:00 Europe/Oslo.
- Innlogging, Husk meg eller bakgrunnstråder.
- Paper Trading- eller produksjonshandelslogikk.

## Utestående
Live Render-test av UI, JSON, PDF, scheduler, Pushover og navigasjon er fortsatt obligatorisk før produksjonsklar status.

## Lokal valideringsstatus
- 624 pytest-tester bestått, 0 feilet, samt 4 beståtte deltester.
- Statisk sikkerhetsaudit og full releaseaudit bestått.
- Representativ 8-siders Investor Edition-PDF rendret og kontrollert lokalt.
