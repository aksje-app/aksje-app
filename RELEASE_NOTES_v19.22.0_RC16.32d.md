# Release Notes — v19.22.0 RC16.32d

## Super Portfolio Completion Plus

RC16.32d lukker de siste åpne punktene i Super Portfolio-masterlisten og legger samtidig inn de fire avtalte beslutningsstøttene.

### Nytt
- 📊 Automatisk indeksbenchmark med valgbart indeksoppsett og alpha mot Super Portfolio.
- 📊 Manuell Aurora-benchmark for sammenligning fra samme startpunkt.
- 🧯 Stress Radar med estimerte marked-, sektor- og valutascenarioer.
- 🖥️ Eget ressurs-panel for cgroup/minne og PostgreSQL-kapasitet.
- 🕒 Data Freshness med FRESH / AGING / STALE / DATA GAP.
- 💸 Turnover og estimert kurtasje/slippage, inkludert nettoavkastning etter kostnader.
- 📅 Event Risk for kommende rapport-/resultatdato når kandidatdata inneholder datoen.
- 🧠 Decision Confidence basert på datakvalitet, ferskhet, regime-fit, signalspredning og korrelasjonsdekning.
- 📄 De nye benchmark-, stress-, confidence- og kostnadsseksjonene er med i Super Portfolio-PDF.
- ✅ Master-checklisten er oppdatert til RC16.32d og er release-gate.

### Drift
- Super Portfolio er fortsatt SHADOW og sender ingen ekte ordre.
- De to eksisterende bannerne på forsiden beholdes uendret; Super Portfolio er fortsatt et vanlig dashboard-vindu under dem.
- Automatisk indeksbenchmark oppdateres i den planlagte Super Portfolio-syklusen ved ny Investment Pipeline-kjøring og kan også oppdateres manuelt fra modulen.
