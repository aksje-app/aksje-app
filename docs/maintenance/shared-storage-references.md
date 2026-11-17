# Felles lagring for kjøringsdata

PostgreSQL-leserne støtter både eldre JSON-dokumenter og versjonerte referanser. Kjente duplikater kan skrives som referanser med `STORAGE_SHARED_REFERENCES_ENABLED=1`. Standard er avslått. Aktivering krever autoritativ PostgreSQL-lagring for analysene og strategiene.

## Lagringskontrakt

- En strategikjøring bevarer en ordnet liste med referanser til uforanderlige beslutningsversjoner. Kjøring, nye beslutninger og de to oppslagsindeksene publiseres i én transaksjon. En NOK-forberedelse bruker referanser til allerede lagrede, identiske snapshots og strategikjøringer. Forberedelsen beholder originale felt når en verifiserbar kilde mangler.
- Siste ordinære markedsrapport, siste pipeline-kjøring, pipeline-forslag og speilet av rapportarkivet kan leses gjennom sine etablerte nøkler. Samtidig skriving av kilden og en ny referanse skjer i én transaksjon. En separat revisjon som ville endret en tidligere publisert visning materialiserer den gamle visningen før oppdateringen.
- En referanse kontrollerer SHA-256 for det materialiserte innholdet. En manglende kilde, feil kontrollsum eller syklus gir en eksplisitt lesefeil. En eksisterende sikkerhetskopi skal beholde både referanser og kilder.
- Den nye OOM-historikken beholder opptil 14 dager med hendelser innen et logisk budsjett på 32 MiB og 256 KiB per kjøring. Siste stegmarkør og stdout fortsetter etter at historikkbudsjettet er brukt opp. Den gamle JSONL-strømmen beholdes med støtte for normal lesing.

## Utrulling

1. Utrull kompatible lesere på alle tjenester som leser eller skriver disse nøklene, med flagget av. Installer NOK-operatørversjon 2026.11.17.1 eller nyere før aktivering på nøkler som operatøren leser.
2. Kjør forløpet før og etter på samme isolerte PostgreSQL-fixture. Sammenlign materialiserte dokumenter, beslutningsrekkefølge, kopibyte inkludert nye referanser, og faktisk endrede indeksverdier. Bruk verifisert kopi av data ved måling av forventet produksjonseffekt. Release-gaten kjører referanser, avbrudd og tilbakerulling.
3. Etter aktivering brukes ordinære kjøringer til å kontrollere resultat, rapporttilgang, omkjøring, DB-vekst og cron-varighet. Følg minst sju sammenlignbare døgn på begge sider, med logiske verdibyte, tabellstørrelse og fysisk diskbruk der den er tilgjengelig. Registrer prisarkiveringen separat.
4. Ved tilbakeføring, slå av nye referanseskrivinger og behold kompatible lesere. Den rullerende telemetrien kan leses med `read_breadcrumb_history(source="rolling")` også etter tilbakeføring. En eldre versjon av programmet krever at eksisterende referanser materialiseres og verifiseres først.

## Sluttkriterier

- Alle testede dokumenter og finans- og læringsjournaler samsvarer før og etter. Ingen referanse mangler kilde, og omkjøring skaper ingen doble handler.
- Sikt mot minst 95 % reduksjon i nye JSON-byte for de identifiserte kopifeltene. Dokumenter endringen i lagrede verdibyte og skriveaktivitet for samme arbeidsmengde. Budsjettet gjelder logiske byte. PostgreSQLs TOAST, indekser, WAL og Render-disk måles separat.
- Beslutningsindeksen endres høyst én gang per ferdig strategikjøring. Identisk publisering gjentar ingen logisk beslutning. Ordinær cron beholder kadens og fullfører uten nye lagringsfeil.
- Midlertidig historikk holder seg innen budsjettet, og siste holdbare steg kan leses etter avbrudd. Beregn tilgjengelig margin til eksisterende lagringsgrense over 90 dager med observert vekstrate og fysisk måling.

Eksisterende historikk og prisarkivets særskilte rutine beholdes. Framtidig arkivering av en referert kilde forutsetter kontroll av alle avhengige lesere, et manifest med eksakte nøkler og summer, verifisert gjenoppretting og separat godkjenning.
