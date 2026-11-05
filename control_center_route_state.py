"""Pure control-center route synchronization helpers."""
from __future__ import annotations

from typing import Any, Callable


def consume_control_center_route_lock_v19220_rc6(
    session_state,
    group_map: dict[str, list[str]],
    panel_map: dict[str, Callable[[], None]],
    group_by_option: dict[str, str],
) -> bool:
    """Synchronize an explicit route before Streamlit radio widgets render."""
    lock = session_state.pop("ai_control_center_route_lock_v19220_rc6", None)
    if not isinstance(lock, dict):
        return False
    panel = str(lock.get("panel") or "").strip()
    group = str(lock.get("group") or "").strip()
    if panel not in panel_map:
        return False
    if group not in group_map or panel not in group_map.get(group, []):
        group = next((name for name, labels in group_map.items() if panel in labels), "")
    if not group:
        return False
    valid_panels = [label for label in group_map.get(group, []) if label in panel_map]
    if panel not in valid_panels:
        return False
    group_option = next((option for option, name in group_by_option.items() if name == group), "")
    session_state["ai_control_center_group_v1863m"] = group
    session_state["ai_control_center_group_v1863aj"] = group
    session_state["ai_control_center_active_panel_v1863m"] = panel
    session_state["ai_control_center_active_panel_v1863aj"] = panel
    session_state["ai_control_center_active_real_panel_v18598"] = panel
    if group_option:
        session_state["ai_control_center_group_radio_v1863aj"] = group_option
    session_state[f"ai_control_center_panel_radio_v1863aj_{group}"] = panel
    session_state.pop("analysis_pipeline_active_stage_v1863bz", None)
    return True


def normalize_selected_panel_aliases(session_state,panel_map):
    """Resolve saved legacy labels to an existing renderer before radio sync."""
    aliases={'Top Picks':'⭐ Analyse – Top Picks','Long Engine':'📈 Analyse – Long Engine',
        'AI Kandidattest':'🤖 AI – Kandidattest','Paper Trading og kontroll':'💼 Handel – Paper Trading',
        'System/admin':'⚙️ Innstillinger – System/admin'}
    def actual(label):
        return aliases.get(label,label) if label not in panel_map and aliases.get(label) in panel_map else label
    for key in list(session_state.keys()):
        if key in {'ai_control_center_active_panel_v1863m','ai_control_center_active_panel_v1863aj','ai_control_center_active_real_panel_v18598'} or str(key).startswith('ai_control_center_panel_radio_v1863aj_'):
            value=session_state.get(key)
            if isinstance(value,str):session_state[key]=actual(value)
    lock=session_state.get('ai_control_center_route_lock_v19220_rc6')
    if isinstance(lock,dict):session_state['ai_control_center_route_lock_v19220_rc6']={**lock,'panel':actual(lock.get('panel',''))}
