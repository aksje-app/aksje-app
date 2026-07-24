"""Safe, explainable approval UI for v19.0.13.

All sensitive configuration and model promotions remain human-gated.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
import json

import streamlit as st


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fmt(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "–" if value is None else str(value)


def _path_get(root: Mapping[str, Any], path: str, default: Any = None) -> Any:
    node: Any = root
    for part in str(path or "").replace("/", ".").split("."):
        if not part:
            continue
        if not isinstance(node, Mapping) or part not in node:
            return default
        node = node[part]
    return node


def approval_details(item: Mapping[str, Any]) -> dict[str, Any]:
    source = str(item.get("approval_source") or "LEARNING").upper()
    if source == "CONFIGURATION":
        try:
            from autonomi_core.configuration.registry import load_registry
            registry = load_registry()
            values = registry.get("values") or {}
        except Exception:
            values = {}
        rows = []
        for path, new_value in dict(item.get("changes") or {}).items():
            old_value = _path_get(values, path)
            rows.append({"Parameter": path, "Gammel verdi": _fmt(old_value), "Ny verdi": _fmt(new_value)})
        return {
            "type": "Konfigurasjonsendring",
            "module": "Sentral autonomikonfigurasjon",
            "reason": item.get("reason") or "Ingen begrunnelse registrert",
            "changes": rows,
            "tests": item.get("test_results") or {"Status": "Ikke dokumentert"},
            "effect": item.get("expected_effect") or "Effekt må vurderes manuelt før aktivering.",
            "risk": item.get("risk") or "Endringen kan påvirke rangering, risiko eller porteføljebeslutninger.",
            "rollback": f"Automatisk konfigurasjonssnapshot opprettes. Basisversjon: {item.get('base_config_version') or '–'}",
        }
    guard = dict(item.get("guard") or {})
    changes = []
    for row in guard.get("risk_changes") or []:
        changes.append({
            "Parameter": row.get("parameter"),
            "Gammel verdi": _fmt(row.get("before")),
            "Ny verdi": _fmt(row.get("after")),
        })
    if not changes:
        changes = [{"Parameter": p, "Gammel verdi": "Se Champion", "Ny verdi": "Se kandidatversjon"}
                   for p in guard.get("changed_parameters") or []]
    return {
        "type": "Modellpromotering",
        "module": "Kontrollert læring",
        "reason": f"Kandidat {item.get('version_id') or '–'} foreslås som ny Champion.",
        "changes": changes,
        "tests": {
            "Endret parameterandel": f"{float(guard.get('changed_parameter_share_pct', 0)):.1f}%",
            "Vesentlig endring": "Ja" if guard.get("major_change") else "Nei",
            "Vesentlig risikoendring": "Ja" if guard.get("material_risk_change") else "Nei",
        },
        "effect": "Ny modellversjon blir aktiv i den teoretiske læringskjeden.",
        "risk": "Fare for overtilpasning eller svak generalisering. Produksjonsendring krever eksplisitt godkjenning.",
        "rollback": "Forrige Champion beholdes i historikken og kan gjenopprettes.",
    }


def render_approval_card(item: Mapping[str, Any], *, key_prefix: str, compact: bool = False) -> None:
    approval_id = str(item.get("approval_id") or "ukjent")
    details = approval_details(item)
    st.markdown(
        f"<div class='approval-id-v1913'><b>{details['type']}</b><br>Teknisk referanse: {approval_id}</div>",
        unsafe_allow_html=True,
    )
    st.caption(f"Opprettet: {item.get('created_at') or '–'} · Modul: {details['module']}")
    st.markdown(f"**Begrunnelse:** {details['reason']}")
    with st.expander("Se endring, test, effekt og risiko", expanded=not compact):
        st.markdown("##### Foreslått endring")
        if details["changes"]:
            st.dataframe(details["changes"], use_container_width=True, hide_index=True)
        else:
            st.info("Ingen detaljert parameterdifferanse er registrert. Godkjenning bør avventes.")
        st.markdown("##### Testresultat")
        st.json(details["tests"], expanded=True)
        st.markdown(f"**Forventet effekt:** {details['effect']}")
        st.warning(f"**Mulig risiko:** {details['risk']}")
        st.info(f"**Reversering:** {details['rollback']}")

    choice_key = f"{key_prefix}_choice_{approval_id}"
    note_key = f"{key_prefix}_note_{approval_id}"
    confirm_key = f"{key_prefix}_confirm_{approval_id}"
    st.text_input("Beslutningskommentar", key=note_key, placeholder="Kort begrunnelse for beslutningen")
    approve, reject = st.columns(2)
    if approve.button("Godkjenn forslag", type="primary", use_container_width=True, key=f"{choice_key}_approve"):
        st.session_state[confirm_key] = "APPROVE"
    if reject.button("Avvis forslag", use_container_width=True, key=f"{choice_key}_reject"):
        st.session_state[confirm_key] = "REJECT"

    pending_choice = st.session_state.get(confirm_key)
    if pending_choice:
        verb = "godkjenne" if pending_choice == "APPROVE" else "avvise"
        st.warning(f"Bekreft at du vil {verb} {approval_id}. Ingen endring aktiveres før bekreftelsen.")
        yes, cancel = st.columns(2)
        if yes.button("Bekreft beslutning", type="primary", use_container_width=True, key=f"{confirm_key}_yes"):
            note = str(st.session_state.get(note_key) or "").strip()
            if not note:
                st.error("Skriv en kort beslutningskommentar før du bekrefter.")
            else:
                approved = pending_choice == "APPROVE"
                if str(item.get("approval_source") or "").upper() == "CONFIGURATION":
                    from autonomi_core.configuration.registry import resolve_approval
                    resolve_approval(approval_id, approved, actor=f"USER: {note}")
                else:
                    from controlled_parameter_learning import resolve_promotion_approval
                    resolve_promotion_approval(approval_id, approved, note=note)
                st.session_state.pop(confirm_key, None)
                st.success("Beslutningen er registrert og lagt i revisjonsloggen.")
                st.rerun()
        if cancel.button("Avbryt", use_container_width=True, key=f"{confirm_key}_cancel"):
            st.session_state.pop(confirm_key, None)
            st.rerun()


def inject_approval_mobile_css() -> None:
    st.markdown("""
    <style>
    .approval-id-v1913{overflow-wrap:anywhere;word-break:break-word;padding:.7rem;border:1px solid rgba(120,170,210,.3);border-radius:.65rem;margin-bottom:.45rem}
    @media (max-width: 768px){
      [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:.55rem!important}
      [data-testid="column"]{min-width:100%!important;flex:1 1 100%!important;width:100%!important}
      div[data-testid="stDataFrame"]{overflow-x:auto!important;max-width:100%!important}
      .approval-id-v1913{font-size:.95rem!important}
      .stButton>button{min-height:44px!important;white-space:normal!important;overflow-wrap:anywhere!important}
    }
    </style>
    """, unsafe_allow_html=True)
