# v19.22.0-rc16.23 – Rapporttest og varige PDF-lenker

## Nytt

- Avhuking under Fullt rapportsenter → Planlegging og avanserte innstillinger.
- Automatisk testrapport med Pushover hvert 30. minutt.
- Knapp for én umiddelbar test.
- Varig status for siste test, rapport-ID og Pushover.
- Automatisk stopp etter fire vellykkede tester, tre feil eller to timer.

## Sikkerhet

Testrapporten kan ikke utføre Autonomi-portefølje, kjøp, salg eller kontrollert læring. Ordinære rapporter prioriteres foran testen, og eksisterende rapportlås hindrer overlapp.

## Rapportlenke

Cron-genererte PDF-er lagres i den autoritative databasen. Pushover bruker en tilfeldig, unotert tokenlenke som åpnes før innlogging og utløper etter 14 dager. Dermed er lenken ikke avhengig av cron-instansens midlertidige disk eller Streamlits sideruting.

Ingen handels-, score-, risiko- eller porteføljeterskler er endret.
