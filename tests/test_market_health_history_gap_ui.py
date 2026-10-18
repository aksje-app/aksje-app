from market_health_ui import render_market_health

class FakeSt:
    def __init__(self): self.messages=[]
    def subheader(self,x): self.messages.append(str(x))
    def caption(self,x): self.messages.append(str(x))
    def info(self,x): self.messages.append(str(x))
    def write(self,*x): self.messages.append(str(x))
    def markdown(self,x,**kwargs): self.messages.append(str(x))
    def expander(self,x): self.messages.append(str(x)); return self
    def checkbox(self,*args,**kwargs): return False
    def __enter__(self): return self
    def __exit__(self,*args): return False

def test_history_gap_is_explained_without_score():
    st=FakeSt()
    render_market_health(st, {"indicators":{"breadth":{"observations":[{"value":55.152,"source":"real","observed_at":"2026-10-16T00:00:00Z"}]}},"composite":{"validated":False}})
    assert any("Historikk og datakvalitet" in v for v in st.messages)
    assert any("Markedsbredde</strong>" in v and "1 daterte observasjoner" in v for v in st.messages)
    assert any("IKKE BEREGNET" in v for v in st.messages)
