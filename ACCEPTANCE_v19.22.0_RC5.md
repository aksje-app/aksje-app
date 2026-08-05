# Akseptansekrav v19.22.0 RC5

RC5 kan ikke produksjonsgodkjennes før følgende er bekreftet på Render:

1. Render Cron registrerer en automatisk valutasyklus innen fem minutter etter deploy.
2. «Hent kurs nå» viser ny kurs, kurstid og status fra samme kjøring.
3. «Sjekk valutagrense nå» henter kurs én gang og bruker samme resultat i UI, runtime og eventuell Pushover.
4. Pushover-testen inneholder fersk kurs, samme status som UI, grenser og kurstid.
5. Feil hos datakilden vises tydelig og gammel kurs merkes ikke som ny.
6. Helkjedetesten etterlater ikke kunstig kurs eller falsk grensestatus.
7. Mobilvisningen har ingen horisontal overflyt i statuskortene; teknisk tabell er lukket som standard.
8. Automatisk helse viser varig cron-status, ikke `NOT_STARTED` fra deaktivert webtråd.
9. Morgen- og kveldsrapport samt øvrige scheduler-jobber fungerer uendret.
