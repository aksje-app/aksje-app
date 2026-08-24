# Deploy RC16.31ad

1. Distribuer FULL-pakken og synkroniser eksisterende Render Blueprint.
2. Kontroller at `aksje-app`, rapport-scheduler og Paper-scanner peker til samme repository, branch og commit.
3. Bekreft at alle tre tjenester fullfører deploy fra samme commit via `autoDeployTrigger: commit`.
4. Kjør én manuell utkastkjøring og la én fast rapport fullføres.
5. Verifiser at webheader, Pushover, JSON og begge PDF-er viser `v19.22.0-rc16.31ad`.
6. Verifiser at Shadow viser grønn kontroll ved reelt samsvar, men fortsatt `SHADOW_READ_ONLY` og `promotion_eligible=false`.
7. Verifiser at Render ikke rapporterer OOM, prosessrestart eller uventet 502 under kjøringen.

Ved commitavvik skal cron fortsatt blokkeres kontrollert. Ikke overstyr commitkontrollen manuelt.
