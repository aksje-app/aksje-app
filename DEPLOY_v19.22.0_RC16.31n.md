# Deploy RC16.31n

1. Verifiser SHA-256 mot leverte sjekksummer.
2. Deploy FULL-pakken, eller DELTA over en verifisert RC16.31m-installasjon.
3. Bevar eksisterende database og persistent disk. Ikke nullstill portefølje, handler, læring eller innstillinger.
4. Kontroller at appen viser `v19.22.0-rc16.31n`.
5. Start ett manuelt utkast og kontroller at PDF/JSON viser samme porteføljeantall og totalsummer.
6. Mens en rapport er aktiv, start ett nytt utkast. Det skal vise ventestatus og låseeier, ikke `FAILED`.
7. Kontroller at avbryt fjerner en ventende manuell jobb sikkert.
8. Verifiser faste kjøringer 08:00 og 22:00 Europe/Oslo.
9. Verifiser UI, offentlig PDF, JSON, logger, scheduler og Pushover.

Versjonen er ikke produksjonsverifisert før punkt 4-9 er dokumentert live på Render.
