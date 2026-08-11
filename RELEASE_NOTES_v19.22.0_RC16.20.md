# v19.22.0-rc16.20 – Background Job Watchdog

Denne utgaven retter fastlåste manuelle rapportkjøringer og gammel jobbstatus som hindret ny kjøring.

## Endret

- Worker-heartbeat og reell fremdrift måles separat.
- PREFLIGHT uten fremdrift frigjøres automatisk etter 150 sekunder. Senere steg har egne, konservative frister.
- En frigitt worker mister jobbleasen og kan ikke publisere et forsinket resultat.
- En ny kjøring kan startes etter `STALLED` uten å slette rapporter eller runtime-data.
- Kontrollert avbrudd er beholdt, med egen sikker frigivelse når et steg står fast.
- UI viser tid siden fremdrift, heartbeat, arbeidsenheter, aktivt objekt og tidsgrense.
- Feilede, avbrutte og fastlåste jobber tilbyr en hemmelighetsfri diagnose-ZIP.
- Fullt rapportsenter åpner som standard i en lett kjørings- og fremdriftsflate. Rapportkropper, historikk, Accuracy Analytics og avanserte jobbinnstillinger lastes først etter eksplisitt valg.

## Uendret

Kjøps-, salgs-, score-, risiko-, evidens-, portefølje-, lærings- og produksjonsterskler er ikke endret.

## Teststatus

- 13 nye og tilgrensende watchdog-/livssyklustester bestått.
- 34 målrettede bakgrunns-, avbrudds-, fremdrifts- og replaytester bestått.
- Full regresjon: 750 bestått, 38 eldre forventningstester feilet. Feilene gjelder eldre versjonsnumre og tidligere rapportpresentasjon som med hensikt ble fjernet av eksportporten; ingen ny watchdog-test feilet.
