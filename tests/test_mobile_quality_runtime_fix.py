from quality_valuation import _safe_ticker, run_screen
from ui_library.shell import render_shell

def test_numeric_oslo_ticker_is_valid():
    assert _safe_ticker("2020.OL") == "2020.OL"

def test_numeric_oslo_ticker_can_run_screen(monkeypatch):
    monkeypatch.setattr("market_universe.market_activation_level", lambda market: "ON")
    result = run_screen(["2020.OL"], lambda ticker: {
        "ticker": ticker,
        "price": 100,
        "trailing_eps": 10,
        "annual_eps": [8, 9, 10],
        "financial_date": "2026-06-30",
        "free_cash_flow": 1,
        "roce_history": [0.15, 0.16, 0.17],
        "industry": "Industrial",
    })
    assert result["selected"] == 1
    assert result["completed"] == 1

class Ctx:
    def __enter__(self): return self
    def __exit__(self,*args): return False

class Fake:
    def __init__(self, pressed=None):
        self.pressed=pressed
        self.session_state={}
        self.query_params={}
        self.labels=[]
        self.reruns=0
    def markdown(self,*args,**kwargs): pass
    def container(self,**kwargs): return Ctx()
    def columns(self,n,**kwargs): return [Ctx() for _ in range(n)]
    def button(self,label,key=None,**kwargs):
        self.labels.append(label)
        return key == self.pressed
    def rerun(self): self.reruns += 1

def test_mobile_labels_have_no_literal_escape_and_navigation_mutates_query():
    st=Fake("aa_mobile_nav_market")
    render_shell(st,"overview")
    assert all("\\n" not in label for label in st.labels)
    assert st.query_params["aa_nav"] == "market"
    assert st.reruns == 1
