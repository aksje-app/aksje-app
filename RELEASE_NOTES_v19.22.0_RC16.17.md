# v19.22.0-rc16.17

- Rapportarkivet viser maksimalt 20 rapportsammendrag per side.
- Lukkede rapporter leser ikke lenger hele den arkiverte kjøringen i bakgrunnen.
- JSON, PDF, tekst, leveransedata, spor og rapportpakkehandlinger lastes bare etter eksplisitt «Last rapportdetaljer».
- ZIP-startfeltet kan derfor bli interaktivt uten å vente på opptil 200 komplette rapportobjekter og PDF-er.
- Sidevelgeren viser tydelig hvilken del av arkivet som er synlig.
- Eksisterende callback-start, polling, watchdog, timeout og karantene er beholdt.
