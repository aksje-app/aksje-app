# Test- og analyseaudit v18.6.3bn

## Konklusjon

Aktiv testsuite bør være nåværende v18.6.3-funksjoner, ikke gamle patchkopier og v18.5-røykprøver som låser appen til historiske UI-detaljer. Full `pytest` plukket tidligere opp gamle mapper og utdaterte tester, noe som ga falske røde feil og importkollisjoner.

## Endret nå

- `pytest.ini` er lagt til og gjør `test_v1863*.py`, `test_alpha_radar*.py` og `test_early_warning_engine.py` til aktiv standard-suite.
- Historiske `patch_v18_*`-mapper ignoreres av pytest.
- Gamle smoke-tester som fortsatt kan være nyttige er ikke slettet, men holdes utenfor standardkjøringen til de eventuelt migreres.
- En v1863-test er oppdatert for dagens harde evidensport: tom nyhetskilde skal gi null Early Warning-funn, ikke en kandidat med tom katalysator.

## Testoverlapp funnet

- Mange gamle v18.5-tester sjekket eksakt `APP_VERSION = "v18.5.89"`. Dette er duplikat av nyere versjonstester og bør ikke være aktiv standard.
- Flere gamle UI-tester leser `app.py` uten UTF-8 og feiler på norske tegn. Dette er teststøy.
- Flere gamle Kontrollsenter-tester sjekker tidligere layoutankere som er erstattet av v18.6.3-navigasjonen.
- Patchmapper inneholder kopier av samme testnavn, som gir importkollisjoner.

## Analysepanel-overlapp

- Alpha Radar og Early Warning deler kilder og evidenslag, men bør ikke slås sammen. Alpha Radar er contrarian/hidden-potential, Early Warning er ferske tidlige signaler.
- Finansavisen Bjellesauer og Aktørregister overlapper på personnavn, men bør holdes adskilt: Finansavisen er import/evidens, Aktørregister er lokal navne- og rollefasit.
- Oljefond Radar og Finansavisen Bjellesauer overlapper på eier-/aktørspor. De bør dele rapport- og evidensformat, men ikke bli én motor.
- Top Picks, Smart AI, Marked/rangering og Auto Test Lab overlapper mest. De bør etter hvert samles på én felles ranking-/universservice og ulike visninger.
- Paper Trading og Porteføljeanalyse skal være koblet, men ikke slått sammen. Paper Trading er beholdningen; Porteføljeanalyse vurderer samlet risiko og forbedringer.

## Anbefalt neste rydding

1. Migrer nyttige v18.5-tester inn i få, moderne v1863-tester.
2. Lag én felles `test_version_and_layout_guards.py` i stedet for mange versjonstester.
3. Lag én felles Streamlit-mock for gamle UI-smoke-tester hvis de skal beholdes.
4. Flytt gamle patchmapper til arkiv utenfor aktiv workspace når zip-leveranser er avklart.
