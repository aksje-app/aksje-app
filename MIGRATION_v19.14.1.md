# Migrering til v19.14.1

v19.14.1 krever ingen destruktiv database- eller porteføljemigrering.

## Konfigurasjon

- Enkel-modus får en egen varig markedsprofil. Manglende profil initialiseres til Norge, Sverige og USA.
- Eldre seksmarkedsoppdrag beholdes som historikk, men brukes ikke stille som ny standardprofil.
- Eksisterende sentrale ekspertregler beholdes og vises i oppsummeringen før start.

## Portefølje

- Eksisterende ordinære og læringsposisjoner beholdes.
- Nye ordinære kjøp må passere den harde v19.14.1-kjøpssperren.
- Ingen historiske handler slettes eller omskrives av migreringen.

## Rapportdata

Nye leveranse-JSON-er bruker kanoniske kandidatreferanser og kompakt historikk. Eldre rapport-JSON-er kan fortsatt leses; ved regenerering flates nestede råkopier ut i rapportvisningen.
