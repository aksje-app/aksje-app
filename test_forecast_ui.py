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
