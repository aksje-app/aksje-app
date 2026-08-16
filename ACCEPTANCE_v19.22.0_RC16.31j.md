# Acceptance – v19.22.0-rc16.31j

## Releasemål

Stabilitets- og observabilitetsutgave som gjør rapport-, evidens-, Shadow-, Paper- og lagringsavvik synlige før de blir produksjonsfeil.

## Obligatoriske porter

- Programmet starter og alle distribuerte Python-filer kan kompileres.
- Mobil rapportlevering bruker byte-nedlasting som primær handling; ekstern PDF er tydelig sekundær.
- Topprangerte evidenskandidater får et faktisk, budsjettavgrenset kildeforsøk også når datakarantene fortsatt blokkerer beslutningen.
- Hver prioritert kandidat får maskinlesbar evidensstatus, og topp 3 rapporteres som komplett/ufullstendig.
- Shadow viser kandidatvis beslutningsdiff og sperrer aktivering når samsvar eller overlapping er under minstekravet.
- Systemkontrollen omfatter rapportkjeden, Paper-heartbeat, Shadow-port, evidensdekning og lagringsretensjon.
- FULL og DELTA valideres uten hemmeligheter, runtime-data eller ugyldige filer.

## Ikke endret

Kjøps-, salgs-, risiko-, score- og porteføljeterskler er ikke senket i denne utgaven. Datakarantene fortsetter å blokkere beslutninger; bare evidensforsøket er frigjort innenfor eksisterende budsjett.
