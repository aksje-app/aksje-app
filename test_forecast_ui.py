import sys
import types

# Minimal Streamlit mock so helper functions can be imported in this environment.
streamlit_mock = types.SimpleNamespace(
    markdown=lambda *a, **k: None,
    caption=lambda *a, **k: None,
    expander=lambda *a, **k: None,
    columns=lambda *a, **k: [],
    text_input=lambda *a, **k: "AAPL",
    selectbox=lambda *a, **k: "1m",
    slider=lambda *a, **k: 50,
    button=lambda *a, **k: False,
    info=lambda *a, **k: None,
    warning=lambda *a, **k: None,
    error=lambda *a, **k: None,
    dataframe=lambda *a, **k: None,
    plotly_chart=lambda *a, **k: None,
)
sys.modules["streamlit"] = streamlit_mock

from forecast_ui import _format_pct, _format_price, _risk_color

assert _format_price(1234.567) == "1,234.57"
assert _format_pct(3.456) == "+3.46%"
assert _format_pct(-1.2) == "-1.20%"
assert _risk_color("Lav") == "green"
assert _risk_color("Medium") == "orange"
assert _risk_color("Høy") == "red"
print("forecast_ui smoke test OK")


from forecast_ui import _extract_ticker_from_value

assert _extract_ticker_from_value({"ticker": "nvda"}) == "NVDA"
assert _extract_ticker_from_value({"symbol": "eqnr.ol"}) == "EQNR.OL"
assert _extract_ticker_from_value("tsla") == "TSLA"
assert _extract_ticker_from_value("this is not a ticker") is None


from forecast_ui import _forecast_cache_key

key = _forecast_cache_key("aapl", "1m", "1y", 50, 0.0)
assert key == "forecast_v1834::AAPL::1m::1y::50::0.0"


from forecast_ui import _strength_color
assert _strength_color(90) == "#22c55e"
assert _strength_color(20) == "#ef4444"
