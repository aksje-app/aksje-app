# Akseptanse v19.22.0-rc16.19

- [x] Mangelfull kandidat kan ikke få `FULL_REPLAY`.
- [x] Manipulert snapshot avvises på kontrollsum.
- [x] Offline replay må gi identisk handling, porter, terskler og blokkoder.
- [x] Kjøp og salg av samme ticker i samme syklus avvises.
- [x] Kontanter og posisjoner avstemmes mot faktiske handlinger.
- [x] Identisk retry gjenbrukes; konflikt mot eksisterende run-ID avvises.
- [x] Replaydata bruker varig lagring og følger med i læringsarkivet.
- [x] Inkrementelt inventar oppdateres først etter verifisert ZIP.
- [x] Ingen handels- eller risikoterskler er endret.
- [x] 75 målrettede tester bestått.
- [x] Full regresjon gjennomført: 748 bestått, 35 eldre forventningstester feilet.

Status: `LOCAL_PASS_LIVE_REQUIRED`. En faktisk ny Render-kjøring må bekrefte første produksjonslagrede `FULL_REPLAY`.
