from ui_library.shell import MOBILE_ROUTES, MORE_ROUTES, render_shell

class Ctx:
    def __enter__(self): return self
    def __exit__(self,*args): return False

class Fake:
    def __init__(self, pressed=None):
        self.pressed=pressed
        self.session_state={}
        self.query_params={}
        self.blocks=[]
        self.reruns=0
    def markdown(self,v,**kwargs): self.blocks.append(str(v))
    def container(self,**kwargs): return Ctx()
    def columns(self,n,**kwargs): return [Ctx() for _ in range(n)]
    def button(self,label,key=None,**kwargs): return key == self.pressed
    def rerun(self): self.reruns += 1

def test_every_primary_mobile_target_changes_navigation():
    expected={"overview":"dashboard","portfolio":"portfolio","market":"market","quality":"quality_valuation","alerts":"alerts"}
    for slug,target in expected.items():
        st=Fake("aa_mobile_nav_"+slug)
        render_shell(st,"overview")
        assert st.query_params["aa_nav"] == target
        assert st.reruns == 1

def test_more_opens_and_every_more_target_navigates():
    st=Fake("aa_mobile_nav_more")
    render_shell(st,"overview")
    assert st.session_state["aa_mobile_more_open"] is True
    for item in MORE_ROUTES:
        st=Fake("aa_mobile_more_"+item.slug)
        st.session_state["aa_mobile_more_open"]=True
        render_shell(st,"overview")
        assert st.query_params["aa_nav"]

def test_mobile_rail_contains_six_primary_actions():
    assert [x.slug for x in MOBILE_ROUTES] == ["overview","portfolio","market","quality","alerts","more"]
