from forecast_backtest_engine import _extract_actual_price_from_series

payload_dt = "2024-01-02T12:00:00+00:00"
from datetime import datetime
forecast_dt = datetime.fromisoformat(payload_dt)
series = [
    {"date": "2024-01-02", "close": 100},
    {"date": "2024-01-03", "close": 101},
    {"date": "2024-01-04", "close": 102},
    {"date": "2024-01-05", "close": 103},
    {"date": "2024-01-08", "close": 104},
    {"date": "2024-01-09", "close": 105},
    {"date": "2024-01-10", "close": 106},
]
actual, meta = _extract_actual_price_from_series(series, "1w", forecast_dt=forecast_dt)
assert actual == 105
assert meta["date_precision"] is True
assert meta["target_date"] == "2024-01-09"
assert meta["actual_date"] == "2024-01-09"
print("forecast_backtest date precise test OK")
