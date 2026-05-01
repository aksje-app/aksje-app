# aksje_app_clean_baseline_v1

Dette er en ryddet produksjonsbase etter hotfix-runden.

## Inneholder
- Siste fungerende auto-buy/paper trading
- Pushover-varsling ved faktisk BUY/SELL
- Ryddet sidebar-struktur
- Børsstatus / market calendar
- Cron-kontroll, pause og full stopp
- Background guard/cache
- Manuell Top Picks-henting når marked er stengt
- Insider hotfix + bakoverkompatibilitet
- force_manual_fetch hotfix
- Samlet systemtest: `check_system.py`

## Anbefalt GitHub-rensing
1. Pakk ut denne ZIP-en lokalt.
2. I repoet:
   ```bash
   git rm -r .
   ```
3. Kopier inn filene fra denne ZIP-en.
4. Ikke legg inn:
   - `__pycache__/`
   - `*.pyc`
   - gamle ZIP-er
   - gamle backupfiler
5. Push til GitHub.
6. Deploy Render.

## Test i Render Shell
```bash
python check_system.py
```

Hvis `check_system.py` passerer, er basen klar for videre utvikling.
