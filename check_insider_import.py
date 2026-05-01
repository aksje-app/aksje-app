from insider import get_insider_data, get_insider_signal, get_insider_transactions

print("Import OK")
for ticker in ["AAPL", "MSFT", "GOOGL"]:
    try:
        data = get_insider_data(ticker)
        print(ticker, "score:", data.get("score"), "latest:", data.get("latest_type"), data.get("latest_date"), "tx:", data.get("transactions"))
    except Exception as e:
        print(ticker, type(e).__name__, e)
