F3 viderefører NOK-regnskap og separat, arkivavhengig restart for Paper, Autonomi og Superporteføljen. Aktivering og handel med restartkontoer er fortsatt sperret utenfor testmiljø. Gamle kontoer, tap og læring beholdes; Superfond bruker sin eksisterende native modell.

Siste kontroll mot main retter et ordinært Autonomi-avvik: eide tickere som faller utenfor kandidatlisten får nå risikotilsyn med dokumentert fersk quote fra kandidat/posisjon eller separat leverandør. Leverandørsvikt med gyldig mottatt quote hindrer ikke risikosalg. Uten gyldig bevis stoppes utførelse eksplisitt; ingen antatt kurs brukes. Strategiterskler er uendret.

Seks felles ordinære prober består på både main og #167. Egne tester dekker stop-loss, delvis gevinstsikring, gevinstvern, kandidatfiltre, leverandørsvikt, lagring, rapporter og sperret oppstartsaktivering. PR #166 er prøvd sammen med #167 i separat testkopi, inklusive samme fond i to grafkontekster og Superfond-suiten/PostgreSQL. Native fondsøkonomi samsvarer med main i tolv kontrollpunkter.

Alle endringer i 33 eksisterende runtime-/verktøyfiler er dokumentert i `docs/mergekontroll-20261023/funksjonsendringer.md`; PR-en er ikke bare en ren tilføyelse av restartkode. Sluttrapport, kommandoer og testtall ligger i samme mappe.

Ingen produksjonsdata er endret eller publisert. Ingen merge, deploy, produksjonsarkivering, nullstilling eller produksjonsaktivering. Yahoo-leverandørtilgang er IKKE VERIFISERT (CONNECT-proxy HTTP 403).

Sluttkjøring etter gjenopptakelse: **2 507 tester + fire deltester besto**, uten feil eller skips (417.19 s). Inkluderer 91 nettleserforløp, 24 PostgreSQL-tester og alle opprinnelige 99 regresjonstilfeller. Alle 154 kompatibilitetstester med #166 og 24 releasekontrakter besto. Superfond-testservere bruker nå isolert dynamisk port. Vurdering: klar for merge som sperret funksjonalitet; ingen produksjonsaktivering.
