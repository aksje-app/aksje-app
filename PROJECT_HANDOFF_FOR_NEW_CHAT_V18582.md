# Overføringsnotat for ny chat — v18.5.82

## Kort kontekst

Dette prosjektet er en Streamlit-basert aksje-/fondanalyseapp med Paper Trading, varslingssystem, fond/ETF-analyse, AI-kontrollsenter, porteføljeanalyse og flere risikomotorer.

Bruker ønsker nå stabilisering, ikke flere nye funksjoner.

## Nåværende base

Start fra:

**v18582_stabilization_handoff_base.zip**

Denne er bygget fra v18.5.81.

## Viktige regler for videre arbeid

- Ikke lag bilder.
- Ikke lag nye funksjonsstormer.
- Ved små rettinger: lag patch-only ZIP med kun endrede filer.
- Ved større milepæl: lag komplett clean ZIP.
- Ikke pakk filer inni ekstra mappe dersom ZIP skal direkte opp på GitHub root.
- Oppdater alltid `app_version.py`.
- Ikke bland filer fra ulike versjoner.
- Kjør minst `py_compile` på endrede Python-filer.
- Sjekk at `app.py` ikke kaller funksjoner som ikke finnes.

## Kjente prioriteringer

1. Runtime-stabilitet først.
2. UI-frys/dimming må holdes borte.
3. Global oppdatering skal være synlig, blå, og ikke flyte over innhold.
4. Paper Trading-posisjoner og handelslogg skal være synlige.
5. Pushover må testes med ekte miljøvariabler.
6. Sikkerhetsmodus bør kobles til faktiske regler eller fjernes/forklares.
7. Fond/aksje-navn skal være konsekvent der metadata finnes.
8. Store visuelle endringer bør gjøres gradvis.

## Viktige filer

- `app.py` — hovedapp, stor og bør refaktoreres senere.
- `app_version.py` — versjonskilde.
- `sticky_topbar.py` — toppbar/status.
- `global_busy.py` — global busy/status-state.
- `paper_trading.py`, `paper_store.py`, `trading_engine.py` — Paper Trading.
- `settings_store.py` — lagrede innstillinger.
- `security_metadata.py` — ticker/fond metadata.
- `core_risk_engine.py`, `portfolio_intelligence_engine.py`, `validation_engine.py`, `factor_timeseries_intelligence.py` — risikomotorer.

## Viktigste lærdom fra siste runde

Tidligere patcher feilet fordi de:
- ble laget fra feil base,
- hadde filer i undermappe i stedet for repo-root,
- blandet `app.py` og hjelpefiler fra ulike versjoner,
- stolte på `py_compile`, som ikke fanger runtime-manglende funksjoner.

Unngå dette ved alltid å starte fra denne komplette basen.
