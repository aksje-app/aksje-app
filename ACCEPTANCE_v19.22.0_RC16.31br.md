# Acceptance – RC16.31br

RC16.31br kan godkjennes når følgende er dokumentert live på Render:

- [ ] Web, scheduler og Paper scanner kjører `v19.22.0-rc16.31br`.
- [ ] Norge-master er autoritativ Euronext-master, ikke `FALLBACK_UNVERIFIED`.
- [ ] Oslo Børs (`XOSL`), Euronext Growth Oslo (`MERK`) og Euronext Expand Oslo (`XOAS`) har hver sin dokumenterte instrumenttelling.
- [ ] Summen er hele den aktuelle offisielle aksjelisten; rapporten viser 100 % rask skannedekning og ingen manglende offisielle symboler.
- [ ] Alle stage-1-aksjer får Fresh Trend-screening før dypanalyse-kuttet.
- [ ] Sterke Fresh Trend-signaler utenfor ordinær topprangering kan reserveres til utvidet analyse uten å endre kjøpsregler.
- [ ] Paper Trade bruker samme Norge-master, med persistent bounded rotasjon gjennom hele universet og prioritet for åpne posisjoner.
- [ ] Børsnavn/MIC/ISIN følger instrumentet gjennom kandidatdata, Fresh Trend, rapport/UI og Paper Trade der data finnes.
- [ ] BQ-minneforbedringen består: komplett rapport har fortsatt god cgroup-margin og ingen OOM.
- [ ] Sluttstatus for rapportkjeden er konsistent `COMPLETED/OK`.

Eksakt antall norske aksjer hardkodes ikke. Det er Euronext-masterens live antall som er fasit.
