# Rettinger etter produksjonsrevisjonen 21. oktober 2026

Utgangspunkt: `main` på `e1e62efdedb0c6efe218d0c0a76c124115276abe`.
Arbeidsgren: `fix/revisjon-transaksjoner-og-jobber`.

Etterfølgende uavhengig sluttkontroll og ytterligere rettinger i samme PR er dokumentert i [2026-10-21-pr162-sluttkontroll.md](2026-10-21-pr162-sluttkontroll.md).

## Programmeringsfeil som rettes

- Planlagte SP-jobber returnerer samme listekontrakt som manuelle jobber. `change_count` er et eget felt. Worker tar ikke lenger `len()` av et heltall.
- En varig oppgjørskvittering knytter jobben/kjøringen til lagrede handler. Nytt forsøk sluttfører status uten å skanne eller bokføre på nytt. Feil etter oppgjør gir DEGRADED og eksplisitt oppgjørsstatus. Den gamle SPJ-20261021-131559-9C8E27 kan gjenkjennes gjennom verifisert pipeline og matchende lagret vurdering. Manglende historiske utførelseskurser konstrueres ikke.
- PostgreSQL lagrer porteføljetilstand, transaksjonsrader og kvittering i én transaksjon med revisjonskontroll og lås. Konkurrerende beslutninger får konflikt fremfor å overskrive hverandre. Lokal utviklingslagring bruker ett atomisk dokument som også inneholder journal/kvitteringer.
- Ordinær vurdering, stoppovervåking og manuelt modellsalg bruker samme oppgjør. Kontanter og beholdningsverdi avstemmes, kostnader trekkes fra og kursendringen registreres før posisjonen fjernes. Kontantandel og kostnadsrapport følger oppgjøret.
- Kjøp, salg, økning og reduksjon får stabil handels-ID, posisjons-ID, prisgrunnlag, observasjonstid, beslutningstid, simulert utførelsestid, salgsårsak, stopnivå, kostnad, kontanter og NAV etter transaksjonen.
- Stoppovervåkingen bruker verifisert ujustert intradagkurs med leverandørtid. Gamle, manglende, fremtidige eller bakoverdaterte kursbevis gir ingen modellhandel. Analysens opprettelsestid erstatter ikke kursobservasjonstid.
- Verifisert neste-sesjonsåpning beholdes som eksplisitt simulert inngangsgrunnlag. En analytisk pris uten tidspunkt brukes ikke som en senere markering av et nytt kjøp.
- UTC-håndtering retter Paper-holdetid og alder. Ukjent/fremtidig holdetid åpner ikke ordinære signalutganger. Gjenkjøpskarantenen undersøker siste salg, ikke det eldste.
- Den eksisterende 24-timers minimumsholdetiden håndheves for ordinære strategiske utganger. Nødvendige risiko- og gevinstsikringsutganger vurderes først. En ordinær SP-rebalansering som krever en for tidlig reduksjon/utgang, utsettes samlet.
- Risikogjenfylling begrenses av godkjente ventende plasser, reelle ledige plasser og eksisterende maksimum per kjøring. Én godkjent plass gir ikke tre kjøp.

## Strategi og historiske begrensninger

Risikoterskler, gevinstsikringstrinn, scoremodell og rangering er ikke endret. Begrensningen av gjenfylling og håndheving av minimumshold er eksplisitt bestilt i rettingsoppgaven; nye optimaliserte handelsterskler innføres ikke.

Oppgjøret viderefører Superporteføljens teoretiske modell med prisavkastning og porteføljeeksponering. Modellenhetene er ikke meglerbekreftede aksjeantall eller en ny valutamodell. Eksisterende lagret NAV og målvekter gir et merket inngående regnskapsgrunnlag ved overgang; historisk NAV korrigeres ikke automatisk. Tidligere tapte BWE/OMC-salgskurser og historiske transaksjoner fylles ikke inn med antakelser.

## Eksport og etterprøvbarhet

Begge SP-diagnosepakker inkluderer `transactions.json`, `transactions.csv` og `transaction_coverage.json` uten den tidligere diagnostikkgrensen på 20/120/150 poster. Dekningsfilen viser antall, periode, regnskapsstart og samme lagrede tilstandsrevisjon som journalen. Tickerdiagnosen inkluderer også `stop_surveillance_history.json`. Det samlede replay-arkivet får Superporteføljens tilstand og journal. Brukerflaten viser siste 250 journalførte handler og peker på full eksport; eldre historikkhull oppgis eksplisitt.

## Validering

Tester kjører mot isolert lokal lagring og en separat PostgreSQL 16-container. Ingen produksjonsdatabase, varsling, merge eller deploy brukes.

- DNO bruker dokumenterte inngangs-/utgangsverdier i regresjonsscenarioet. BWE/OMC-testene bruker eksplisitte scenario-kurser; produksjonsfilene manglet deres eksakte salgskurser.
- Jobben med to lagrede kjøp fullfører; feil etter oppgjør og nytt forsøk gir ingen ny skanning eller ekstra bokføringer.
- PostgreSQL-tester injiserer feil etter både transaksjons- og tilstandsskriving. Hele oppgjøret rulles tilbake. Samtidige like jobber gir én journalføring; samtidige forskjellige revisjoner gir én konflikt.
- UTC, tidssoneoffset, sommertidsovergang, ukjent holdetid, umiddelbar stop-loss, gevinstsikring, strategisk salg etter minimumshold, begrenset gjenfylling, kontanter/NAV, prosessgjenstart og full journaleksport kontrolleres.

Resultater i dette miljøet:

| Kontroll | Resultat |
| --- | --- |
| Målrettede regresjoner, eksisterende exit-/databeviskontroller og fire PostgreSQL-tester | 87 bestått |
| Utvalgte eksisterende SP-, diagnostikk- og rapporttester | 114 bestått |
| Hele «Quality regression suite» fra eksisterende CI-arbeidsflyt | 478 bestått |
| Aktiv testsamling uten eldre versjonsfiler og direkte Yahoo-akseptanse | 589 bestått, 7 valgfrie nettlesertester hoppet over |
| Release-kontraktskript fra quality_release_gate | 24 bestått |
| Python-kompilering, PDF-avhengigheter, fem rapportdelingskontroller og diff-kontroll | Bestått |

Samlingene overlapper og skal ikke summeres. De to eksisterende direkte Yahoo-akseptansetestene fikk CONNECT 403 i skymiljøet; de er ikke verifisert bestått. Sju eldre kontrakttester er kjørt på uendret main og feiler også der: seks utdaterte versjonskrav og én eksisterende forventning om prioritering av eide aksjer i kvalitetsplanleggeren. Disse feilene skjules eller endres ikke i denne rettingen.
