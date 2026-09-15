from pages.overview import build_overview_page, render_ab_overview
class _Context:
    def __enter__(self): return self
    def __exit__(self,*args): return False
class FakeStreamlit:
    def __init__(self): self.html=[]; self.buttons=[]
    def markdown(self,value,**kwargs): self.html.append(value)
    def columns(self,spec): return [_Context() for _ in range(spec if isinstance(spec,int) else len(spec))]
    def button(self,label,**kwargs): self.buttons.append(label); return False
    def caption(self,value): pass
    def rerun(self): raise AssertionError("unexpected rerun")
def test_ab_overview_is_a_real_decision_workspace():
    st=FakeStreamlit(); model=build_overview_page([],pending_approvals=0,scheduler_ok=True)
    render_ab_overview(st,model,navigate=lambda route: None); html="".join(st.html)
    assert "aa-overview-hero" in html and "BESLUTNINGSOVERSIKT" in html and "Krever oppmerksomhet" in html
    assert st.buttons == ["Kjør eller åpne rapport","Åpne Super Portfolio","Se marked og kandidater","Åpne drift"]
