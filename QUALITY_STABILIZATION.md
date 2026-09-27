# Quality-modul: stabiliseringskontrakt

Denne modulen er funksjonsfryst mens stabilisering pågår. Nye funksjoner skal ikke
blandes inn i feilretting før kontrakten under er grønn.

## Harde PASS/FAIL-krav

1. Kvalitet -> Rapportvalg -> Kort PDF -> Rapportvalg.
2. Kvalitet -> Rapportvalg -> Full PDF -> Rapportvalg.
3. Kvalitet -> Rapportvalg -> Diagnose -> Rapportvalg.
4. Kvalitet -> Rapportvalg -> ZIP -> fil åpnes separat, rapportvalg beholdes.
5. Rapportvalg -> Kvalitet.
6. Ingen kvalitetsrapport-retur får falle tilbake til Start.
7. PDF-retur finnes på alle sider og er ikke utskrivbar.
8. V2 svakere + V2 sterkere = aktive uenigheter når klassifisering finnes.
9. Eldre V2-data uten klassifisering merkes som ikke klassifisert; 5 = 0 + 0 er forbudt.
10. 5 stjerner krever minst 4/5 i alle fire hoveddimensjoner.
11. QUALITY/IMPROVING kan ikke ha review_reason QUALITY_WEAK.
12. Kvalitetsselskap/Attraktiv kandidat kan ikke ha kvalitetsscore under 3/5.
13. Prisfelt bruker valuta; P/E er eksplisitt multippel.
14. Gamle lagrede rader får scenarioavstand beregnet ved visning når grunnlaget finnes.
15. Tidligere release-tester skal ikke svekkes for å få grønn status. Endret kontrakt krever ny, streng akseptansetest.

## Definition of done

"Ferdig" betyr at målrettet test, integrasjonstest og hele Quality-release-gaten
er grønn. Produksjonsadferd som avhenger av iOS/Safari må i tillegg merkes som
produksjonskontroll frem til den er bekreftet på en faktisk telefon.
