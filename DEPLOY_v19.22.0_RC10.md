# Deploy v19.22.0 Investor Edition RC10

## Grunnlag

Deploy RC10 FULL som ren kodeerstatning over RC9. Behold databaser, runtime-disk, rapportarkiv, logger, cache, `.env` og hemmeligheter utenfor kildepakken.

## Fremgangsmate

1. Ta sikkerhetskopi av varig Render-disk og produksjonskonfigurasjon.
2. Pakk ut RC10 FULL lokalt.
3. Erstatt repository-koden med hele FULL-pakken.
4. Commit og push hele endringssettet.
5. Bekreft `v19.22.0-rc10` i Render-logg og program.
6. Kjør full akseptanse i `ACCEPTANCE_v19.22.0_RC10.md`.
7. Apne Rapporter -> Drift og kontroller evidenssoksdiagnostikken for siste kjøring.
8. Kjør evidensauditen mot minst en ny live rapport-JSON og kontroller at ukjent arsaksstatus er 0 og budsjettavvik er 0.

## Auditkommando

```bash
python tools/audit_evidence_search_v19220_rc10.py REPORT.zip --trades autonomous_trades.zip --output-dir audit_rc10
```

Auditen genererer ingen PDF og endrer ingen produksjonsparametere.

## Scheduler

- Morgen: 08:00 Europe/Oslo
- Kveld: 22:00 Europe/Oslo

## Tilbakerulling

Rull kode tilbake til siste fungerende commit. Ikke overskriv varig runtime eller database med innhold fra ZIP-pakken.
