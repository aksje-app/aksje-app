# AI Aksje Analyzer Pro

Denne versjonen har:
- smartere scoremodell
- P/E, kvalitet, vekst og gjeld
- momentum og trend
- risiko og drawdown
- nyheter/sentiment
- bedre backtesting med transaksjonskostnad, stop-loss og benchmark

## Start lokalt

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Render start command

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 10000
```

## Environment variables

```text
NEWSAPI_KEY
FINNHUB_API_KEY
```

Ikke investeringsråd.
