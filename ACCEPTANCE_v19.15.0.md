# Akseptanse v19.15.0

Versjonen kan ikke godkjennes før alle punktene nedenfor er dokumentert.

## Ren installasjon

- Installer kun fra låst `requirements.txt` og Git-commit.
- Oppstartskontroll, runtime-importkontroll og PDF-smoke består.
- Ingen skjult PostgreSQL-tilkobling i lokal lagringsmodus.
- `python tools/audit_full_system_v19150.py` returnerer `ok: true`.
- GitHub-kilden inneholder ingen mutable filer under `.app_runtime`, `data`, `logs`, `runtime` eller `storage`.
- Feilet Pushover-respons registreres som feilet og ikke som sendt.

## Markedsprofil

- Kjernemarkeder kjører nøyaktig Norge, Sverige og USA.
- Utvidet Norden kjører Danmark og Finland.
- Brasil og hvert enkeltmarked kan kjøres separat.
- Jobb, investeringsoppdrag, runtime-logg, JSON og PDF viser samme markeder.

## Kilder og rapport

- Irrelevante nyheter avvises og logges med årsak.
- Insiderposter viser primær eller sekundær proveniens uten å overdrive verifikasjon.
- Modellkonfidens, evidensjustert modellkonfidens og beslutningskonfidens er identiske mellom alle rapportseksjoner der samme mål vises.
- Evidensdekning beregnes fra evidens, ikke markedsdata.
- Kandidat- og porteføljebegrunnelse er identiske.
- Semantisk integritetsport blokkerer bevisst manipulerte markeder, konfidens, nyheter og porteføljebegrunnelse.

## Drift

- Innlogging virker på første forsøk og Husk meg overlever deploy.
- Aktiv meny beholdes gjennom en hel Autonomi-kjøring.
- JSON og PDF genereres og kan lastes ned på PC og mobil.
- Testdatabase/persistent disk er isolert fra produksjon.

## Paper Trading

- Paper Trading forblir AV under de øvrige testene.
- Blokkert handel oppretter ingen ordre, posisjon eller transaksjon.
- Først etter øvrig godkjenning testes ett manuelt kjøp og ett salg i isolert testportefølje.
- Automatisk Paper Trading åpnes ikke i samme godkjenningssteg.
