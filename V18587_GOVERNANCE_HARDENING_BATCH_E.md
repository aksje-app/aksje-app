# v18.5.87 — Governance Hardening Batch E

Scope: D2 Protected zones + D4 Feature governance + D8 In-app changelog.

## Endret
- La til `governance_registry.py` med protected zones og changelog/build-historikk.
- Utvidet Safe build-panelet til å vise:
  - regresjonssjekk
  - feature-status
  - protected zones
  - hva er nytt / build-historikk
  - audit-logg
- Utvidet feature-registeret med governance-funksjoner.
- Oppdatert versjon/build-ID til `v18.5.87`.
- La inn regresjonsankere for `Protected zones`.

## Ikke endret
- Ingen omskriving av analysemotorer.
- Ingen endring i forecast/risk/fund engines.
- Ingen endring i cash-/kjøpsalgoritmene utover metadata/visning.

## Formål
Gjøre videre GO-runder tryggere ved å synliggjøre hvilke områder som er beskyttet, hvilke features som er aktive/partial, og hvilken build som faktisk kjører.
