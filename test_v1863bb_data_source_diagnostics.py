import os
from pathlib import Path

from alpha_radar_enrichment import enrich_alpha_radar_row
from data_source_diagnostics import (
    build_data_source_status,
    horizon_to_days,
    horizon_to_months,
    probe_market_data_sources,
    summarize_source_error,
)
from runtime_env import data_source_env_status, load_app_env, redact_secrets


def _reset_runtime_env(monkeypatch):
    import runtime_env

    monkeypatch.setattr(runtime_env, "_ENV_LOADED", False)
    monkeypatch.setattr(runtime_env, "_ENV_SOURCES", [])


def test_runtime_env_loads_nested_env_file_without_exposing_secret(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "FINNHUB_API_KEY=test_finnhub_secret_123456\n"
        "NEWSAPI_KEY=test_newsapi_secret_987654\n",
        encoding="utf-8",
    )
    _reset_runtime_env(monkeypatch)
    monkeypatch.setattr("runtime_env.candidate_env_paths", lambda: [env_file])
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)

    load_app_env()
    status = data_source_env_status()

    assert status["env_loaded"] is True
    assert any(Path(path).name == ".env" for path in status["env_sources"])
    assert "FINNHUB_API_KEY" in os.environ
    assert "NEWSAPI_KEY" in os.environ
    redacted = redact_secrets("https://example.test?token=abc123secret&apiKey=xyz789secret")
    assert "secret" not in redacted
    assert "token=***" in redacted


def test_horizon_controls_data_windows(monkeypatch):
    _reset_runtime_env(monkeypatch)
    monkeypatch.setenv("FINNHUB_API_KEY", "test_finnhub_key")
    monkeypatch.setenv("NEWSAPI_KEY", "test_newsapi_key")

    assert horizon_to_months("1m") == 1
    assert horizon_to_months("3m") == 3
    assert horizon_to_months("6m") == 6
    assert horizon_to_months("12m") == 12
    assert horizon_to_days("12m") == 372

    status_rows = build_data_source_status("6m")
    assert any(row["Vindu"] == "6 mnd" for row in status_rows)
    assert any(row["Kilde"] == "Finnhub insider" for row in status_rows)
    assert status_rows[0]["Kilde"] == "Miljo/API-nokler"
    assert status_rows[0]["Status"] in {"env-fil lest", "nokler i miljo"}
    assert summarize_source_error("insiderkilde", "403 Forbidden for url token=abc123") == "insiderkilde: ikke tilgang/dekning for valgt marked"
    assert summarize_source_error("nyhetskilde", "too many requests recently") == "nyhetskilde: API-kvote brukt opp"


def test_enrichment_passes_horizon_to_data_providers():
    calls = {"insider": None, "earnings": None, "news_days": None}

    def insider_provider(ticker, months=6):
        calls["insider"] = months
        return {
            "score": 0.7,
            "buy_count": 1,
            "sell_count": 0,
            "latest_type": "BUY",
            "latest_transactions": [{"name": "Kari CEO", "relation": "CEO", "type": "BUY"}],
        }

    def earnings_provider(ticker, months=4):
        calls["earnings"] = months
        return {"days_until": 45, "date": "2026-07-01", "error": None}

    def news_provider(query, limit=8, source="manual", days_back=None):
        calls["news_days"] = days_back
        return ([{"title": "Contract", "description": "strong order"}], None)

    row = enrich_alpha_radar_row(
        {"ticker": "TEST.OL", "name": "Test ASA", "market_cap": 1_000_000_000},
        ticker="TEST.OL",
        include_news=True,
        include_insider=True,
        include_results=True,
        news_provider=news_provider,
        insider_provider=insider_provider,
        earnings_provider=earnings_provider,
        horizon="12m",
    )

    assert calls["insider"] == 12
    assert calls["earnings"] == 12
    assert calls["news_days"] == 372
    assert row["insider_evidence"][0]["type"] == "Insider"
    assert row["earnings_days_until"] == 45


def test_probe_market_data_sources_classifies_errors_and_empty_results():
    def insider_provider(ticker, months=3):
        if ticker.endswith(".ST"):
            return {"transactions": [], "error": "unsupported symbol"}
        return {"transactions": 1, "latest_transactions": [{"name": "CEO"}], "error": None}

    def earnings_provider(ticker, months=3):
        return {"days_until": None, "date": None, "error": None}

    def news_provider(query, limit=3, source="manual", days_back=None):
        return ([], "Mangler NewsAPI-nokkel")

    rows = probe_market_data_sources(
        horizon="3m",
        insider_provider=insider_provider,
        earnings_provider=earnings_provider,
        news_provider=news_provider,
        markets=["USA", "Sverige"],
    )

    assert rows[0]["Insider"] == "1 treff"
    assert rows[1]["Insider"] == "0 treff"
    assert "ticker/marked ikke stottet" in rows[1]["Forklaring"]
    assert "API-nokkel mangler" in rows[0]["Forklaring"]



