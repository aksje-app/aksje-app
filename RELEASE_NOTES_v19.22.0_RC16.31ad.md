# RC16.31ad release notes

RC16.31ad bygger direkte på RC16.31ac og er en ren stabiliseringsversjon.

- Shadow-sammenligningen bruker samme beslutningsvokabular som den autoritative kjeden. HOLD, REVIEW og SKIP blir ikke lenger feilaktig omgjort til BUY på grunnlag av en rådgivende strategiscore.
- Shadow forblir eksplisitt skrivebeskyttet og kan ikke promotere eller aktivere noe, også når kontrollstatusen er grønn.
- Læringsaksept godtar kandidater som er dokumentert avvist i den kanoniske porteføljebeslutningen. De krever ikke en kunstig ekstra læringsrad.
- Råverdier som finnes, men som med vilje ikke kan scores, behandles nøytralt. Dette fjerner `float(None)`-feil for blant annet negativ P/E og nullvolum.
- Regresjonstest dekker nøyaktig feilbildet 48 HOLD, 2 REVIEW og 10 SKIP som tidligere ga falskt 16,67 % samsvar.

Ingen scoreterskel, risikogrense, porteføljeregel, handelsregel, datakilde eller datainnhentingsomfang er endret.
