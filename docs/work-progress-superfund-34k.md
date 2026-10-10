# RC16.34k – fremdrift og Superfond-diagnose

## Rettet produksjonsfunn

Bildet viste 1 725,7 MiB minne-headroom og host load per CPU 2,15. Den gamle grensen på host load < 1,5 stoppet Superfond uten at målet dokumenterte containerens CPU-bruk. Host load brukes nå bare som diagnostikk. CPU-utsettelse krever tilgjengelig cgroup v2 CPU-pressure (`some avg10`) på minst 50 %, fra en cgroup med endelig CPU-kvote. Ukjent/ugyldig CPU-mål blokkerer ikke alene. Minnegrensen på 384 MiB, felles eksekveringslås og små batcher beholdes. Dette er ikke en måling av prosent CPU-utnyttelse, og faktisk Render-måledekning må sjekkes etter deploy.

Ressursutsettelse får separate årsakskoder, målinger og tidspunkt. Fire utsettelser over minst én time uten katalogfremdrift gir ett Pushover-varsel når varsling er aktiv. Første kapasitetstilgang etter varslet stopp gir en gjenopptakelsesmelding; den hevder ikke at resultatet er ferdig.

## Felles fremdriftsvisning

- Eksisterende SP-/rapportjobber bruker felles render med arbeidstilstand, fase, antall, tid og sist registrerte aktivitet. 100 % vises bare ved bekreftet COMPLETED; avbrutte/feilede prosesser er ikke ferdige.
- Superfond teller faktiske lagrede katalogsider. Total vises først når begge kildenes antall er kjent. Sideskanning, produktdetaljer, modell/shadow og lagring har egne faser.
- Synkrone ventesteder som tidligere brukte Streamlit-spinner i appen, Analyse, Top Picks og Long Engine bruker aktivitetsstatus. Uten kjent total oppgis dette eksplisitt; ingen tid/prosent anslås.
- Auto Test Lab, fondstester, rangering, porteføljeanalyse og kandidattest beholder sine callbacks/steg, med lagret status. Den tidligere porteføljeanalysen som viste alle fem steg før selve analysen er erstattet med ukjent total under faktisk analyse.
- Bakgrunnslæring, shadow, historiske grunnlag, Superfonds historiske tester og Strategilab registrerer start/slutt. Historiske fondsvarianter og Strategilab-datasett rapporterer reelle enheter underveis.
- Et globalt statusfragment leser lagret SP, Superfond, Paper/Autonomi-skanner, manuell rapportstatus og de siste aktivitetene hvert 15. sekund. Ingen analyser startes av polling. Statusloggen er begrenset til 40 aktiviteter; oppdateringer av enheter skrives tidligst hvert andre sekund.

En RUNNING-post uten bekreftet sluttstatus betyr sist registrert tilstand, ikke en garanti for at en worker overlevde nettbrudd. Avsluttede synkrone steg er merket som steg, ikke som ferdig samlet handels-/rapportjobb. En generell jobbkø, automatisk restart av alle synkrone UI-kall og instrumentering inne i alle tredjepartsfunksjoner er ikke innført. Ukjente totaler bruker aktivitetsvisning.

## Superfond rapporter og diagnose-ZIP

Rapportfeltet forklarer hvorfor PDF/CSV/Excel mangler før første komplette vurdering. Diagnose-ZIP kan lages allerede da. Etter komplett vurdering lages rapportfilene eksplisitt med fremdrift og gjenbrukes for samme snapshot i sesjonen; de bygges ikke ved hver statusoppdatering.

ZIP inneholder snapshot (hovedmodell, shadow-regler/-resultater/-handler, læring, forslag og kandidater), parametre/audit/kvitteringer, jobb/forespørsel/kapasitetsvarsling, katalogindeks, kurs/FX, nyheter, produktdetaljer og lagret historikk. Historikk sjekkes mot original SHA-256, pakkes ut, maskeres og eksporteres som lesbar JSON. Kontroller viser manglende snapshot/referanseperiode, kapitalavvik mellom shadow og hovedmodell, duplisert ISIN, negativ kontantbeholdning, sjekksumfeil og fremtidige kurs-/observasjons-/detaljdatoer i inkluderte rammer.

`manifest.json` oppgir filer, størrelser, sjekksummer og eksakte utelatelser. Samlet råfilbudsjett og ZIP-budsjett er 32 MiB. Læring/historikk prioriteres foran katalogbulk. Derfor betyr ZIP ikke nødvendigvis at all lagret historikk er inkludert eller kontrollert; manifest og README angir dette. Ingen nye kursoppslag, strategiforsøk eller parameterendringer skjer ved eksport. Hemmelige felter maskeres, også inne i komprimert historikk. Eksport krever vanlig innlogget app; ingen offentlig ZIP publiseres.

Siden viser læringsfase og manglende parrede datoer, fryste shadow-regler, felles start, paret meravkastning og siste kjøps-/salgsbegrunnelser. Rådiagnose er flyttet under lesbare målinger. Mobilknappene får ikon og tekst på separate linjer, og syv-ruters layout oppdateres.

## Verifikasjon

Målrettede tester dekker falsk host-load-blokkering, reelt minne/CPU-press, ugyldig måledata, ZIP før snapshot, læring/shadow/historikk, fremtidslekkasje, maske av komprimert historikk, budsjettert utelatelse, UI-knapp, varsel/gjenopptakelse og ærlig progresjon. Release gate kjører dessuten eksisterende regresjon, aktive tester og PostgreSQL-tester før merge. Fysisk mobil og faktiske Render-/Pushover-målinger må bekreftes etter deploy. Denne endringen er ikke merget eller deployet under implementeringen.
