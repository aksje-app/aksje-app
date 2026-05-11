
from datetime import datetime, timezone, timedelta

from forecast_engine import build_all_horizons
from forecast_store import get_forecast_vs_actual_series


def _payload():
    prices = [100 + i * 0.5 for i in range(120)]
    start = datetime(2026, 5, 11, tzinfo=timezone.utc)
    return {"ticker": "AAPL", "horizons": build_all_horizons("AAPL", prices)}, prices, start


def test_actual_history_stops_at_today_and_future_is_none():
    payload, prices, start = _payload()
    actual_dates = [(start - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(44, -1, -1)]
    series = get_forecast_vs_actual_series(payload, prices[-45:], "1m", actual_dates=actual_dates)

    assert series["actual_history_x"][-1] == series["today_label"]
    assert series["forecast_x"][0] == series["today_label"]
    assert series["actual_has_future_values"] is False
    assert all(v is None for v in series["actual"][series["future_start_index"]:])


def test_chart_rows_have_explicit_actual_today_forecast_types():
    payload, prices, _start = _payload()
    series = get_forecast_vs_actual_series(payload, prices[-35:], "1m")
    rows = series["chart_rows"]

    assert rows
    assert rows[-1]["type"] == "forecast"
    assert any(row["type"] == "actual" for row in rows)
    assert any(row["type"] == "today" for row in rows)
    assert any(row["type"] == "forecast" for row in rows)
    assert all(row.get("actual") is None for row in rows if row["type"] == "forecast")
    assert series["series_types"] == {
        "actual_history": "actual",
        "today_marker": "today",
        "forecast_future": "forecast",
    }


def test_forecast_series_is_not_blended_with_actual_series():
    payload, prices, _start = _payload()
    series = get_forecast_vs_actual_series(payload, prices[-60:], "1m")

    assert len(series["forecast_x"]) == len(series["forecast_base"])
    assert len(series["forecast_x"]) == len(series["forecast_bull"])
    assert len(series["forecast_x"]) == len(series["forecast_bear"])
    assert series["labels"][: len(series["actual_history_x"]) - 1] == series["actual_history_x"][:-1]
    assert series["labels"][len(series["actual_history_x"]) - 1 :] == series["forecast_x"]
