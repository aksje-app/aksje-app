from pathlib import Path
import py_compile

from banner_tools import parse_banner_csv_text, parse_banner_settings, parse_ticker_text, merge_ticker_maps


ROOT = Path(__file__).resolve().parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="ignore")


def test_manual_banner_ticker_parser_handles_one_many_and_separators():
    assert parse_ticker_text("YAR.OL") == ["YAR.OL"]
    assert parse_ticker_text("YAR.OL, orkla.ol; acr\nSTB.OL") == ["YAR.OL", "ORKLA.OL", "ACR", "STB.OL"]
    assert parse_ticker_text("YAR.OL, YAR.OL,,") == ["YAR.OL"]


def test_banner_settings_respects_visible_markets_and_deliberate_empty_fields():
    settings = {
        "live_banner_markets_visible": ["Norge", "Sverige"],
        "live_banner_tickers": {"Norge": "YAR.OL", "Sverige": "", "USA": "AAPL"},
    }
    parsed = parse_banner_settings(
        settings,
        ["USA", "Norge", "Sverige"],
        {"USA": "MSFT", "Norge": "EQNR.OL", "Sverige": "VOLV-B.ST"},
        {"YAR.OL": "Yara"},
    )
    assert parsed == (("Norge", "YAR.OL", "Yara"),)


def test_banner_csv_import_add_and_replace_modes():
    imported = parse_banner_csv_text("ticker,market\nYAR.OL,Norge\nORKLY.OL,Norge\nVOLV-B.ST,Sverige\n", default_market="Norge")
    assert imported == {"Norge": ["YAR.OL", "ORKLY.OL"], "Sverige": ["VOLV-B.ST"]}

    added = merge_ticker_maps({"Norge": "EQNR.OL"}, imported, mode="Legg til")
    assert added["Norge"] == "EQNR.OL, YAR.OL, ORKLY.OL"

    replaced = merge_ticker_maps({"Norge": "EQNR.OL"}, imported, mode="Erstatt marked")
    assert replaced["Norge"] == "YAR.OL, ORKLY.OL"


def test_v18615_static_guards_for_discussed_ui_tasks():
    for name in ["app.py", "app_version.py", "trading_engine.py", "banner_tools.py", "auth.py"]:
        py_compile.compile(str(ROOT / name), doraise=True)

    app = _read("app.py")
    version = _read("app_version.py")
    trading = _read("trading_engine.py")
    auth = _read("auth.py")

    assert 'APP_VERSION = "v18.6.24"' in version
    assert "Sarskilt bannerklikk, fart og kompakte knapper" in version
    assert "Importer tickere" in app
    assert "parse_banner_csv_text" in app
    assert "merge_ticker_maps" in app
    assert "special_watch_banner_enabled_v18615" in app
    assert "special_watch_banner_speed_seconds_v18615" in app
    assert ".ticker-tape-wrap.follow-up .ticker-tape-track" in app
    assert 'target=\'_self\'' in app
    assert "Kjopsbelop" in app
    assert "estimated_stock_shares" in app
    assert "amount_override=float(stock_amount or 0.0)" in app
    assert "def paper_buy(ticker, price, confidence=0, reason=\"BUY signal\", trade_context=None, amount_override=None)" in trading
    assert "localStorage" in auth and "remember_token" in auth
    assert "div[data-testid=\"stLinkButton\"] > a" in app
    assert "v18.6.19: final compact action style" in app
    assert "width: 22px;" in app and "font-size: 0.92rem;" in app






