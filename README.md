# AI Aksje Analyzer - komplett versjon

## Start på PC
Pakk alt ut i:

```text
C:\aksje_app
```

Installer:

```bash
python -m pip install -r requirements.txt
```

Start:

```bash
python -m streamlit run app.py
```

eller dobbeltklikk:

```text
start_app.bat
```

## API-nøkler
Lag filen `.env` i `C:\aksje_app`.

Bruk `.env.example` som mal:

```text
NEWSAPI_KEY=din_newsapi_nokkel
FINNHUB_API_KEY=din_finnhub_nokkel
```

## Mobil hjemme på samme Wi‑Fi
Dette er ikke en App Store-app. PC-en kjører appen, mobilen åpner den i nettleser.

1. PC og mobil må være på samme Wi‑Fi.
2. Dobbeltklikk `start_app_mobil.bat`.
3. Bruk Network URL som vises i terminalen.
4. Hvis du ikke ser den, finn PC-IP med:

```bash
ipconfig
```

Eksempel:

```text
IPv4 Address: 192.168.1.45
```

Åpne på mobil:

```text
http://192.168.1.45:8501
```

## Online 24/7
Bruk Render/Railway/Streamlit Cloud. Startkommando:

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port $PORT
```

Legg inn `NEWSAPI_KEY` og `FINNHUB_API_KEY` som environment variables.

## Backtesting
Fanen `Backtesting` har:
- strategi-backtest: modellen rangerer aksjer hver måned
- enkel kjøp-og-hold test
- strategi vs benchmark
- drawdown
- valgte aksjer per måned

Ikke investeringsråd.
