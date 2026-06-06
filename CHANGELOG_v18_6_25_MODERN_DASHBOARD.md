# v18.6.25 – Modernisert hovedside og raskere særskilt banner

## Endret
- Modernisert hovedsiden med nytt premium toppfelt, glass-/kortpreg, bedre bakgrunn og mer oppdatert AI Kontrollsenter-stil.
- Strammet inn visuell prioritet i toppområdet uten å endre analysemotor, ranking, paper trading eller datakilder.
- Særskilt overvåking har fått reell hastighetsmapping: slider 1–100 gir ca. 95s til 8s i stedet for at maks hastighet fortsatt var ca. 40s.
- Særskilt banner er fortsatt uavhengig av hovedbanneret når modus er `Egen fart`.
- Når modus er `Arv hovedbanner`, bruker særskilt banner fortsatt hovedbannerets sekunder med vilje.

## Testet
- `python -m compileall -q .` OK
- `python -m pytest -q test_v18624_special_banner_auth_speed_buttons.py` OK, 5 passed

## Endrede filer
- app.py
- workspace_layout.py
- app_version.py
- test_v18624_special_banner_auth_speed_buttons.py
- CHANGELOG_v18_6_25_MODERN_DASHBOARD.md
