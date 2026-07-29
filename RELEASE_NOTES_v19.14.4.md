# AI Aksje Analyzer Pro v19.14.4 – Driftgjenoppretting

v19.14.4 er en avgrenset stabiliseringsversjon for rask og sikker tilbakeføring til normal analyse- og rapportdrift.

## Rettet

- Autentisering kan bruke en separat `AUTH_DATABASE_URL` uten tilgang til produksjonens `DATABASE_URL`.
- Lokal brukerlagring ligger under `APP_RUNTIME_ROOT/data/auth` eller `AUTH_STORAGE_ROOT`, ikke i Git-repositoryet.
- Render stopper før førstegangsoppsett når autentiseringslageret er flyktig og varig lagring er påkrevd.
- Første admin blir logget inn automatisk og trenger ikke logge inn en gang til.
- «Husk meg» bruker miljøavgrenset cookie, slik at test og produksjon ikke deler sesjoner.
- Remember-token lagres bare som hash på serversiden.
- Passordendring og deaktivering øker brukerens sesjonsversjon og ugyldiggjør gamle sesjoner.
- Navigasjonsstatus lagres per bruker under runtimeområdet.
- Autonomi-statusfragmentet tar et navigasjonskontrollpunkt og gjenoppretter aktiv meny dersom bakgrunnsoppdateringen forsøker å endre den.
- Manuell statusoppdatering bruker fragment-rerun og ikke full app-rerun.
- Testbanneret viser om brukerlager og Paper-lager er varige, og om normal drift er klar.

- Rapportintegritet og den kanoniske JSON/PDF-kontrollen fra v19.14.3 beholdes uendret.

## Avgrensning

Paper Trading aktiveres ikke automatisk. Kontrollert Paper Buy-test åpnes først når testmiljøet har varig bruker- og Paper-lagring og de eksisterende handelssperrene er bestått.
