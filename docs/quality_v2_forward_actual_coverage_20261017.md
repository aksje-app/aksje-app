# Quality V2 / Deep-value: faktisk tilgjengelig datagrunnlag (kontroll 17. oktober 2026)

Produksjonsdata hentet med leseadgang fra Render Postgres:
- `quality_v2_shadow/state`: 54 fullførte kjøringer, 18 evaluerte selskaper, 10 vurdert sterkere i V2 og 4 registrerte svekkelsestilfeller.
- `quality_valuation/latest`: 18 detaljerte Quality V2-rader.
- V2-radene har **ikke** `decision_date` eller `entry_price`. Dermed er dokumentert 7- og 30-handelsdagers avkastning **ikke beregnbar** direkte fra disse radene.
- Et annet Shadow-sett har 2 497 historiske kursmålinger, men dette er ikke dokumentert samme beslutninger/kohort som Quality V2. Ikke slå sammen disse som om de representerte identiske handler.
- Deep-value trenger original beslutningsdato, historisk justert inngangs-/sluttkurs, regnskapets publiseringsdato samt benchmark på samme dato. Ingen dokumentert sammenligning finnes ennå.

`services/quality_v2_forward_evidence.py` implementerer en read-only, fail-closed 7/30-*handelssesjons*-sammenligning som avviser ufullstendige inndata i stedet for å finne på resultater. Den er ikke koblet til automatisk handel eller produksjonskjøring.

Neste produktive arbeid er å registrere original Quality V2-beslutningsdato og historisk justert inngangskurs ved opprettelse av nye observasjoner, og føre uavhengig historisk datakilde med as-of-regnskapsinformasjon for Deep-value. Det krever en separat, verifiserbar fremtidsserie før avkastningssammenligningen kan konkluderes.
