# v18.5.66 Fund Type Adapter

Dette laget gjør at én felles Core Risk / Portfolio Intelligence / Validation-stack kan brukes på ulike fondtyper uten at alt tolkes som aksjefond.

## Ny modul

- `fund_type_adapter.py`

## Hovedfunksjoner

- `canonicalize_fund_type()`
- `get_fund_type_profile()`
- `build_fund_type_adapter()`
- `adapt_rows_for_fund_type()`
- `build_fund_type_aware_analysis()`

## Støttede profiler

- aksjefond
- indeksfond / ETF
- sektorfond
- globalt fond
- kombinasjonsfond
- rentefond
- high yield-fond
- pengemarkedsfond
- alternativt fond / hedgefond

## Hva adapteren styrer

- relevante primærfaktorer
- sekundærfaktorer
- stress-scenarier
- optimizer constraints
- regimepreferanser
- datakrav
- analyse-dybde

## Resultat

Samme motor kan nå brukes på alle fondtyper, men med fondtype-spesifikk risikoforståelse.
