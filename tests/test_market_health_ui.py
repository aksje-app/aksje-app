from datetime import datetime, timedelta, timezone
from market_health_ui import INDICATORS, GROUPS, _valid, render_market_health


class FakeSt:
    def __init__(self):
        self.metrics = []
        self.messages = []
    def subheader(self, text): self.messages.append(text)
    def caption(self, text): self.messages.append(text)
    def info(self, text): self.messages.append(text)
    def write(self, *args): self.messages.append(str(args))
    def markdown(self, text, **kwargs): self.messages.append(text)
    def metric(self, name, value): self.metrics.append((name, value))
    def columns(self, n): return [self for _ in range(n)]
    def expander(self, name): self.messages.append(name); return self
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def progress(self, *args, **kwargs): self.messages.append("score")


def test_twelve_measures_and_explanation_links_exist():
    assert len(INDICATORS) == 12
    assert len({key for _, keys in GROUPS.values() for key in keys}) == 12
    st = FakeSt()
    render_market_health(st, {})
    assert len(st.metrics) == 12
    assert sum(str(x).startswith("ℹ️ Forklaring:") for x in st.messages) == 12
    assert any("IKKE BEREGNET" in x for x in st.messages)


def test_measurement_must_have_source_and_timezone_and_not_future():
    now = datetime.now(timezone.utc)
    good = {"value": 22, "source": "Cboe", "observed_at": (now - timedelta(minutes=5)).isoformat()}
    assert _valid(good)
    assert not _valid({**good, "source": ""})
    assert not _valid({**good, "observed_at": (now + timedelta(days=1)).isoformat()})
    assert not _valid({**good, "value": float("nan")})


def test_unvalidated_composite_never_displays_green_score():
    st = FakeSt()
    render_market_health(st, {"composite": {"risk_score": 15, "validated": False}})
    assert "score" not in st.messages
    assert any("IKKE BEREGNET" in x for x in st.messages)


def test_valid_measurement_preserves_source_and_time():
    st = FakeSt()
    render_market_health(st, {"indicators": {"vix": {"value": 21.5, "source": "Cboe", "observed_at": datetime.now(timezone.utc).isoformat()}}})
    assert ("VIX fryktindeks", "21.50 indeks") in st.metrics
    assert any("Cboe" in x for x in st.messages)
