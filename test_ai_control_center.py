import sys, types

class SS(dict): pass
class Ctx:
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def metric(self, *a, **k): return None

def columns(spec, **k):
    n = len(spec) if isinstance(spec, list) else int(spec)
    return [Ctx() for _ in range(n)]

st = types.SimpleNamespace(
    session_state=SS(),
    markdown=lambda *a, **k: None,
    expander=lambda *a, **k: Ctx(),
    caption=lambda *a, **k: None,
    tabs=lambda labels: [Ctx() for _ in labels],
    info=lambda *a, **k: None,
    success=lambda *a, **k: None,
    warning=lambda *a, **k: None,
    write=lambda *a, **k: None,
    dataframe=lambda *a, **k: None,
    columns=columns,
    metric=lambda *a, **k: None,
    button=lambda *a, **k: False,
    selectbox=lambda *a, **k: "Alle lagrede prognoser",
    radio=lambda *a, **k: "Kort",
    slider=lambda *a, **k: 6,
    text_input=lambda *a, **k: "",
    multiselect=lambda *a, **k: [],
    number_input=lambda *a, **k: 10,
    json=lambda *a, **k: None,
)
sys.modules["streamlit"] = st

from ai_control_center import _compact_alert_status, render_ai_control_center
assert "Varselsenter" in _compact_alert_status() or "Varsler" in _compact_alert_status()
assert callable(render_ai_control_center)
print("ai_control_center smoke test OK")
