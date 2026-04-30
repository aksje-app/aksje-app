"""
Broker adapter - IKKE AKTIVERT.

Denne filen er kun en trygg struktur for senere ekte trading.
Ingen ekte ordre sendes her.

Neste nivå kan koble til f.eks. Interactive Brokers eller Alpaca,
men først etter lang paper trading-test.
"""

LIVE_TRADING_ENABLED = False


def place_order(ticker, side, amount, order_type="market"):
    if not LIVE_TRADING_ENABLED:
        return {
            "ok": False,
            "message": "Live trading er deaktivert. Dette er kun en sikker placeholder.",
        }

    raise NotImplementedError("Broker API ikke koblet til ennå.")
