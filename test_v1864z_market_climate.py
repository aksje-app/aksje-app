from __future__ import annotations

from pathlib import Path
import py_compile


ROOT = Path(__file__).resolve().parent


def _series(start: float, step: float, n: int = 260) -> dict:
    return {
        "dates": [f"2026-{((i // 22) % 12) + 1:02d}-{(i % 22) + 1:02d}" for i in range(n)],
        "close": [round(start + step * i, 2) for i in range(n)],
        "volume": [100000 + i * 750 for i in range(n)],
    }


def test_v1864z_market_climate_engine_contract():
    for name in ["market_climate_engine.py", "market_climate_ui.py", "app.py", "workspace_layout.py", "app_version.py"]:
        py_compile.compile(str(ROOT / name), doraise=True)

    from market_climate_engine import build_market_climate_snapshot, market_climate_report_html, market_climate_to_csv, market_climate_to_json

    snapshot = build_market_climate_snapshot(
        {
            "sp500": _series(100, 0.22),
            "nasdaq": _series(100, 0.30),
            "osebx": _series(100, 0.14),
            "vix": _series(18, -0.01),
            "us10y": _series(45, -0.01),
            "brent": _series(75, 0.03),
            "usdnok": _series(10.8, -0.002),
        },
        manual_inputs={"us_ipo_count": 95, "osebx_price_book": 1.95, "aaii_bullish_pct": 38},
        generated_at="2026-05-31T12:00:00",
    )

    assert snapshot["version"] == "v1864z"
    assert snapshot["climate_score"] >= 55
    assert snapshot["confidence"] >= 70
    assert "Runde 1" in snapshot["round_note"]
    assert {row["Faktor"] for row in snapshot["factor_rows"]} >= {
        "Bred trend og momentum",
        "Volatilitet og frykt",
        "Renter og likviditet",
        "Verdsettelse",
        "Sentiment",
        "IPO og spekulasjon",
    }
    assert snapshot["chart_series"]

    csv_text = market_climate_to_csv(snapshot)
    json_text = market_climate_to_json(snapshot)
    html_text = market_climate_report_html(snapshot)

    assert "Bred trend og momentum" in csv_text
    assert '"climate_score"' in json_text
    assert "Markedsklima rapport" in html_text
    assert "<svg" in html_text
    assert "Skriv ut / lagre som PDF" in html_text


def test_v1864z_market_climate_control_center_contract():
    app = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")
    layout = (ROOT / "workspace_layout.py").read_text(encoding="utf-8", errors="ignore")
    version = (ROOT / "app_version.py").read_text(encoding="utf-8", errors="ignore")

    assert 'APP_VERSION = "v18.6.4z"' in version
    assert "Market Climate Module Foundation" in version
    assert "Markedsklima er lagt inn som egen modul" in version
    assert "Runde 1 er beslutningsstøtte" in version
    assert "from market_climate_ui import render_market_climate_panel" in app
    assert '("Markedsklima", render_market_climate_panel)' in app
    assert '"markedsklima"' in layout
