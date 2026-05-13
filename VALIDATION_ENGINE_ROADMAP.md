# v18.5.65 Validation Engine

Validation Engine er tredje lag i hedgefond-arkitekturen:

```text
Core Risk Engine
  -> Portfolio Intelligence Engine
  -> Validation Engine
```

## Lagt til

- `validation_engine.py`
- `test_v18565_validation_engine.py`
- app-versjon oppdatert til `v18.5.65 Validation Engine`

## Hva Validation Engine gjør

### 1. Walk-forward validation
Tester om ranking og target weights er stabile fra snapshot til snapshot.

Måler:

- rank drift
- top-5 overlap
- target turnover
- pass/review per overgang

### 2. Stress replay
Replayer Core Risk stress-scenarier:

- equity selloff
- tech/AI selloff
- rate shock
- credit stress
- USD/NOK down
- liquidity crunch

Flagger porteføljer som får tosifret estimert stress-drawdown.

### 3. Regime replay
Kjører Portfolio Intelligence Engine under flere regimevekter:

- balanced
- risk_off
- rate_shock
- credit_stress
- risk_on

Måler hvor mye ranking og target weights endrer seg mot balanced baseline.

### 4. Survivorship/data checks
Fanger enkle problemer før backtestresultater tolkes for hardt:

- manglende symboler
- duplikater
- symboler som forsvinner mellom snapshots

## Designvalg

Validation Engine er bevislaget, ikke en ny optimizer. Den skal fortelle når Core Risk + Portfolio Intelligence er robuste nok, og når resultatene bør merkes som `review`.

## Neste naturlige steg

- Koble UI-panel til validation summary
- Lag lagring av validation-runs i `storage/validation_engine/`
- Legg til faktisk historisk avkastning når datakilde er klar
- Legg til benchmark-relative validation
