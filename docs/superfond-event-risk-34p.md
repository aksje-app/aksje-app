# RC16.34p – hendelsesrisiko og gevinstvern

Superfond har en separat modellmotor. Den hadde 6 % trailing stop og 7 dagers ordinær ISIN-karantene, mens aksjenes Superportefølje allerede hadde maks 3 % og andre karanteneregler. Superfond begrenses nå til maks 3 %, også ved gamle lagrede parametre og shadow-regler. Gevinstgulvet kan fortsatt være strammere. Ordinær Superfond-karantene på 7 dager beholdes. Superporteføljens aksjeregler er uendret.

## Brasil-vindu og kjøpsvern

11.–25. oktober 2026, i America/Fortaleza, er Brasil-eksponering begrenset til 10 % av modellkapitalen ved nye kjøpsbeslutninger og utførelse. Eksisterende posisjoner og ventende kjøpsallokeringer inngår. Grensen gjelder investeringsrisiko, ikke ISIN-prefiks, fondsdomisil eller handelsvaluta. Detaljvekter brukes når kjent. Brasil-indeksnavn brukes som konservativ 100 % øvre grense. Manglende landfordeling, globale eller latinamerikanske regionetiketter gir konservativ mulig eksponering; de presenteres aldri som dokumentert 100 % Brasil-investering. Dette kan begrense også globale fond med utilstrekkelige landdata. Kapital som sperres kan bli stående som kontanter.

Valgdatoen 25. oktober er bekreftet av TRE-SP: https://www.tre-sp.jus.br/comunicacao/noticias/2026/Maio/eleicoes-2026-outubro-tem-datas-do-1o-e-do-2o-turnos-definidas-pela-constituicao . Kandidatenes navn eller forventet politisk kursreaksjon brukes ikke som handelsregel. Hendelsesradaren viser kontrollvindu 19.–23. oktober. Varsel sendes ved første fullførte katalogkontroll i vinduet, ikke av en ny separat tidsjobb. Fondsfrister og senere kursobservasjon er fortsatt nødvendige; datoen garanterer ikke utførelse før valget.

## Nedsalg og kvitteringer

Over grensen foreslår modellen konkrete delvise reduksjoner til samlet 10 % øvre eksponering. Godkjenn/Avvis finnes i risikooversikten. Klikk lagrer en atomisk kvittering og køer arbeid; ingen portefølje endres i UI. Worker kontrollerer beholdning, kurs og fortsatt behov. Nye NAV-er ugyldiggjør ikke godkjenningen av samme beholdning. En endret beholdningsmengde gjør kvitteringen foreldet; en kvittering kan aldri brukes to ganger. Ved mindre behov begrenses reduksjonen til den godkjente andelen. Avslag gjelder den konkrete vurderingen; vesentlig endret grunnlag kan gi et nytt forslag. Dette er modellhandler, ingen meglerordre.

Hard stopp gjelder straks ved observert grensebrudd, uten at et nedsalgsforslag må godkjennes. Mykt trendsalg krever to ulike svake kursdatoer. Gjentatte skanninger teller ikke som bekreftelser. Varslingsnivåene vises ved 1,5 % og 2,25 % under topp. Stoppris er aldri en garanti for salgskurs.

## Hendelseskarantene og overlapp

Risikosalg av mulig Brasil-eksponering i hendelsesvinduet sperrer samme ISIN, andre produkter med mulig Brasil-eksponering og produkter med minst 40 % kjent felles toppbeholdningsvekt. Minst 5 hendelsesdager, eksisterende lengre 7-dagers Superfond-karantene og sperre til 26. oktober kl. 00 i Brasil kombineres med den lengste fristen. Deretter kreves to ulike ferske kursdatoer som oppfyller de positive kjøpskravene. En NAV merket før sperrens utløp teller ikke. Salgsbeslutninger før valget som først utføres etterpå får også karantene. Ventende risikosalg hindrer erstatningskjøp, og salg og kjøp i samme syklus kontrolleres igjen. Bekreftelsesregister per exit begrenses til 512 instrumenter; eventuell utskifting utsetter gjenkjøp, aldri forkorter sperren.

Oppgitt overlapp er bare kjent toppbeholdningssnitt. Manglende full beholdningsdekning er ikke null overlapp. Kontrollen omfatter eide og ventende fond og gjentas ved kjøpsutførelse.

## Risikovisning og datagrenser

UI og rapporter viser konservativ Brasil-eksponering, landdatadekning, salgsforslag, karantener, felles toppbeholdninger, hendelsesvindu og risikoindikator 0–100. Indikatoren er en synlig regelberegning: opptil 50 for konsentrasjon, 25 for observert porteføljefall og 25 for aktiv hendelse. Den er ikke en validert risikomodell.

Stresstest bruker aksjer −10 % og valuta −10 %, kombinert multiplikativt til −19 %, på øvre Brasil-eksponering. Dette er scenarioaritmetikk, ikke et løfte om fremtidig kurs. Historisk BRL-bidrag kan ikke beregnes fra handelsvaluta alene; visningen oppgir at underliggende valutadata mangler. En automatisk historisk valutaoppdeling eller komplett beholdnings-/korrelasjonsanalyse er ikke dokumentert.

Ingen nye markedsoppslag i UI og ingen utvidede katalogbudsjetter. Risikodata publiseres sammen med snapshot. Kvitteringer tas med i diagnose-ZIP. Ved overgang til nye regler beholdes gammel modell-/shadow-handels- og kapitalhistorikk; en ny læringsperiode starter, og tidligere læringsdata beholdes separat. Normaliserte shadow-regler publiseres eksplisitt slik at vist stopprosent stemmer med den utførte regelen.

## Verifikasjon

Målrettede tester dekker eide/ventende eksponeringer, endret landvekt ved fill, eldre stopparametre, delvis regnskapsføring, replay/stale kvittering, NAV-endringer, samme-syklus exits, alternative fond, to kursdatoer, lokal datogrense, overlapp og UI-godkjenning. Release gate inkluderer disse testene og PostgreSQL-/mobilnettleserkontroller. Lokal mobilnettleser kunne ikke installeres fordi browser-nedlastingen ikke ga gyldig ZIP; disse kontrollene må bekreftes i CI. Merge og produksjonsdeploy er separate steg.
