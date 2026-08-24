# Valideringsrapport RC16.31ac

## Resultat

- Full pytest: **969 bestått, 0 feilet, 66 dokumenterte historiske strict-xfail, 4 subtester bestått**.
- Målrettet RC16.31ac-regresjon: **33 bestått, 0 feilet, 1 historisk xfail**.
- Versjons- og sporbarhetsaudit: **PASS**.
- Fullsystemaudit: **PASS**, ingen advarsler og ingen endrede produksjonsparametere.
- Navigasjons- og rerun-audit: **PASS**.
- Kompakt hovedrapport: visuelt kontrollert side for side, tre A4-sider uten overlapp eller avkuttet innhold.
- Short og innsider: synlig for topp 3, per marked og i porteføljetabellen. `UKJENT`, `IKKE SØKT`, `INGEN HENDELSER` og kildefeil skilles eksplisitt.
- Deploykontrakt: alle tre Render-tjenester har `autoDeployTrigger: commit`; scheduler og scanner stanser kontrollert ved commit-/versjonsavvik mot webtjenesten.
- Læringskø: eldste aktive observasjonskohort per ticker bevares til modning; nyere dubletter markeres `SUPERSEDED` og historikken holdes avgrenset.

## Produksjonsgrense

Koden og pakkene er en produksjonskandidat. Før endelig produksjonsgodkjenning kreves én live-kontroll etter Blueprint-synkronisering i Render: web, rapport-scheduler og paper-scanner skal vise samme commit og neste Pushover/PDF skal vise `v19.22.0-rc16.31ac`.
