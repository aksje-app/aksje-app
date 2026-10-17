from datetime import datetime, timedelta, timezone
from market_health_history import normalize, summarize
from market_health_ui import render_market_health


def row(days, value, source="Testkilde"):
    return {"observed_at": (datetime.now(timezone.utc)-timedelta(days=days)).isoformat(), "value": value, "source": source}


def test_history_windows_require_actual_baselines():
    values = [row(31, 90), row(8, 95), row(2, 98), row(0, 100)]
    result = summarize("gold", values)
    assert result["count"] == 4
    assert all(result["history"][w]["status"] == "MEASURED" for w in ("24t", "7d", "30d"))
    assert result["history"]["30d"]["difference"] == 10


def test_missing_history_never_implies_zero_move():
    result = summarize("vix", [row(0, 20)])
    assert result["history"]["7d"]["status"] == "INSUFFICIENT_HISTORY"


def test_stale_data_are_visible_but_not_current():
    assert normalize("vix", row(2, 22))["status"] == "STALE"
    assert normalize("cape", row(2, 40))["status"] == "CURRENT"
    assert normalize("vix", {"value": 22, "source": "", "observed_at": row(0, 22)["observed_at"]}) is None


def test_ui_marks_outdated_quotes_explicitly():
    class Stub:
        def __init__(self): self.metrics=[]
        def subheader(self,*a): pass
        def caption(self,*a): pass
        def info(self,*a): pass
        def progress(self,*a,**k): pass
        def markdown(self,*a,**k): pass
        def write(self,*a,**k): pass
        def metric(self,*a): self.metrics.append(a)
        def columns(self,n): return [self for _ in range(n)]
        def expander(self,*a): return self
        def __enter__(self): return self
        def __exit__(self,*a): return False
    ui = Stub()
    render_market_health(ui, {"indicators": {"vix": row(2, 22)}})
    assert ("VIX fryktindeks", "Utdatert") in ui.metrics
