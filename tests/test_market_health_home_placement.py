from pathlib import Path


def test_legacy_dashboard_renders_market_health_before_banners():
    source = Path("app.py").read_text(encoding="utf-8")
    anchor = source.index("# Market health precedes both market banners on the legacy front page.")
    next_banner = source.index("render_live_market_banner()", anchor)
    second = source.index("render_special_watch_banner_surface_v18620()", next_banner)
    assert anchor < next_banner < second
    assert "render_market_health(st)" in source[anchor:next_banner]


def test_new_home_renders_health_before_overview_hero():
    source = Path("pages/overview.py").read_text(encoding="utf-8")
    render = source[source.index("def render_ab_overview("):]
    assert render.index("render_market_health(st_module)") < render.index('aa-overview-hero')
