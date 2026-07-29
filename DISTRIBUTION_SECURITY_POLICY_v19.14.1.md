# Distribusjonssikkerhet v19.14.1

Releasearkivene skal ikke inneholde:

- `.env`, API-nøkler, passord, tokens eller private nøkler
- runtime-mapper, rapportarkiv, databaser, logger eller brukerdata
- cache, `__pycache__`, testcache eller midlertidige filer
- symbolske lenker eller usikre arkivstier

Alle filer listes med størrelse og SHA-256 i `DISTRIBUTION_MANIFEST.json`. Validatoren kontrollerer profilinnhold, versjon, hemmelighetsmønstre, forbudte stier og manifestintegritet. `.env.example` kan inkluderes bare med tomme eksempelverdier.
