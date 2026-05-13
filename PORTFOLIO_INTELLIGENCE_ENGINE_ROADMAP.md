# Portfolio Intelligence Engine Roadmap - v18.5.62

Dette dokumentet er laget for flytting til ny chat og videre arbeid.

## Nåværende stadium
Prosjektet er nå i tidlig Portfolio Intelligence Engine-stadie. Det er ikke full hedgefond-motor ennå, men systemet har et solid fundament:

- Fond-/ETF-analyse med navn + ticker
- Full starter-universe ranking før visningsgrense
- Global-knapp og UI-freeze cleanup
- Layer 1: Base Fund Scoring
- Layer 2: Explainable Fund Intelligence
- Layer 3: Holdings-Aware Fund Analysis
- Layer 4: Insider Intelligence
- Layer 5: Composite Intelligence Score
- Layer 6: What Changed Intelligence
- Layer 7: Scenario & Regime Engine
- Layer 8: Portfolio Fit Engine
- Foundation Stabilization
- Consolidated Intelligence Architecture
- Explanation & Risk Engine
- Portfolio Intelligence Foundation

## Konsoliderte hovedmoduler

### A. Intelligence Core
Holder styr på felles datastruktur, vekting, confidence og freshness.

### B. Explanation & Risk Engine
Standardiserer forklaringer, risikoflagg, positiv/negativ/neutral påvirkning og ikke-black-box logikk.

### C. Portfolio Intelligence Foundation
Samler overlap-cache, regime memory og “Why this portfolio?”-grunnlaget.

## Hva som mangler før full hedgefond-motor

1. **Ekte datadekning**
   - kvalitetssikret holdings-data
   - insider-data med kilde/ferskhet
   - kredittdata, duration, yield, spread
   - sektor/faktor/geografi-normalisering

2. **Faktor- og eksponeringsmodell**
   - growth/value/momentum/quality
   - duration, credit beta, equity beta
   - valuta, råvarer, tech/AI, likviditet
   - indirekte eksponeringer gjennom holdings

3. **Korrelasjon og dependency graph**
   - skjulte avhengigheter
   - single point of failure
   - overlap på faktor-nivå, ikke bare holdings-nivå

4. **Stress Testing Engine**
   - rentehopp, kredittspread, aksjefall, tech/AI-selloff, valuta, likviditet
   - porteføljeeffekt per scenario

5. **Portfolio Construction / Optimizer**
   - foreslå beste kombinasjon av fond
   - mål, risiko, overlap, scenario-robusthet og rebalansering

6. **Adaptive Weighting**
   - vekter endres etter regime og datakvalitet

7. **Backtesting og walk-forward testing**
   - historisk rangering, out-of-sample, overfitting-kontroll

8. **Risk Budgeting**
   - hvor risikoen faktisk kommer fra: rente, kreditt, tech, valuta, enkeltposisjoner

9. **Execution/Rebalancing Layer**
   - når handle, hvor mye, kostnad, skatt, slippage, turnover-kontroll

10. **Governance / Audit Trail**
   - datakilder, vekter, confidence, anbefalingsendringer og alternativer

## Neste anbefalte arbeid
Ikke legg på flere store features før disse er vurdert:

1. Kjør app manuelt og sjekk UI rundt fondanalyse, global-knapp og resultater.
2. Verifiser at Layer 1–8 faktisk vises i UI på relevante steder.
3. Bygg datakildeadaptere for ekte holdings/insider/faktor-data.
4. Deretter: Stress Testing Engine som første store hedgefond-nivå modul.

---

## v18.5.63 byggesteg: 3-lags hedgefondstruktur

De tidligere 7 punktene er nå samlet i tre operative lag for å unngå uoversiktlig modulspredning.

### 1. Core Risk Engine
Ny modul: `core_risk_engine.py`

Samler:
- holdings-normalisering
- faktorgraph
- faktor-eksponeringer
- skjulte dependency/overlap-risikoer
- stress testing
- risk budgeting

Hovedfunksjoner:
- `normalize_risk_holdings(...)`
- `infer_factor_exposures(...)`
- `build_factor_graph(...)`
- `run_stress_tests(...)`
- `build_risk_budget(...)`
- `build_core_risk_profile(...)`

### 2. Portfolio Intelligence Engine
Ny modul: `portfolio_intelligence_engine.py`

Samler optimizer, risk budgeting constraints og adaptive regimevekter i ett lag etter Core Risk Engine.

Hovedfunksjon:
- `build_portfolio_intelligence_profile(...)`

### 3. Validation Engine
Ny modul: `validation_engine.py`

Samler stress validation, regime replay-forberedelse og senere walk-forward/backtesting.

Hovedfunksjon:
- `build_validation_profile(...)`

### Testdekning
Ny testfil:
- `test_v18563_core_risk_engine.py`

Dekker:
- faktorgraph
- stress testing
- risk budget
- samlet Core Risk Engine-profil
- kobling til Portfolio Intelligence Engine og Validation Engine

### Viktig designvalg
Core Risk Engine er bygget deterministisk og uten nettverkskall. Det betyr at den kan brukes trygt i UI, tester, backtesting og senere optimizer uten å introdusere latency eller eksterne avhengigheter.

---

## v18.5.64 byggesteg: Portfolio Intelligence Engine utvidet

`portfolio_intelligence_engine.py` er nå løftet fra enkel rangering til et samlet porteføljelag som kombinerer:

- optimizer-style scoring
- target weights
- trade deltas
- turnover control
- max position constraints
- risk budgeting policy
- adaptive regime presets
- factor cap checks
- forklarbare kandidat-scores

Nye hovedobjekter/funksjoner:

- `PortfolioConstraints`
- `REGIME_PRESETS`
- `score_candidate(...)`
- `optimize_target_weights(...)`
- `build_risk_budget_policy(...)`
- `build_portfolio_intelligence_profile(...)`

Regimer støttet nå:

- `balanced`
- `risk_on`
- `risk_off`
- `rate_shock`
- `credit_stress`
- `growth`

Ny testfil:

- `test_v18564_portfolio_intelligence_engine.py`

Verifisert med:

```bash
python -m pytest -q test_v18563_core_risk_engine.py test_v18564_portfolio_intelligence_engine.py
```

Resultat:

```text
9 passed
```

## v18.5.67 - Factor Time-Series Intelligence

Added `factor_timeseries_intelligence.py` as the temporal intelligence layer:

- dynamic factor series normalization
- rolling factor exposures
- regime transition detection
- latent beta drift diagnostics
- temporal stress propagation path
- online/adaptive factor memory with exponential decay

This turns static factor/risk analysis into a living factor-memory system that can be updated observation by observation.
