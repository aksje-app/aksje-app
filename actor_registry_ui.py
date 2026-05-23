from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import streamlit as st

from actor_registry import (
    ACTOR_TYPES,
    STRENGTH_LEVELS,
    load_actor_registry,
    normalize_actor_row,
    save_actor_registry,
)


def _rows_from_editor(value: Any) -> list[dict[str, Any]]:
    if hasattr(value, "to_dict"):
        try:
            records = value.to_dict("records")
            return [normalize_actor_row(row) for row in records if isinstance(row, Mapping)]
        except Exception:
            pass
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [normalize_actor_row(row) for row in value if isinstance(row, Mapping)]
    return []


def render_actor_registry_panel() -> None:
    st.subheader("Aktørregister")
    st.caption(
        "Redigerbare navn og alias for bjellesauer, institusjoner og insider-watch. "
        "Registeret brukes i Alpha Radar/Early Warning til aa merke hvem som er hvem naar navn dukker opp i eier-, insider- eller nyhetsspor."
    )
    rows = load_actor_registry()
    active_count = sum(1 for row in rows if row.get("active"))
    st.info(f"{len(rows)} aktorer i registeret, {active_count} aktive. Ingen nettverkskall kjores her.")

    edited = st.data_editor(
        rows,
        key="actor_registry_editor_v1863bd",
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "active": st.column_config.CheckboxColumn("Aktiv"),
            "name": st.column_config.TextColumn("Navn"),
            "aliases": st.column_config.TextColumn("Alias", help="Skill alias med komma eller semikolon."),
            "market": st.column_config.TextColumn("Marked", help="Alle, Norge, Sverige, Danmark, Finland, USA, Brasil eller egen tekst."),
            "actor_type": st.column_config.SelectboxColumn("Type", options=list(ACTOR_TYPES)),
            "strength": st.column_config.SelectboxColumn("Styrke", options=list(STRENGTH_LEVELS)),
            "notes": st.column_config.TextColumn("Notater"),
            "links": st.column_config.TextColumn("Lenker"),
        },
    )
    clean_rows = _rows_from_editor(edited)

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        if st.button("Lagre aktørregister", key="actor_registry_save_v1863bd", type="primary", use_container_width=True):
            saved = save_actor_registry(clean_rows)
            try:
                from alpha_radar_enrichment import reset_bjellesau_watchlist_cache

                reset_bjellesau_watchlist_cache()
            except Exception:
                pass
            st.success(f"Lagret {saved} aktorer.")
    with c2:
        st.download_button(
            "Last ned JSON",
            data=json.dumps(clean_rows, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="aktorregister.json",
            mime="application/json",
            use_container_width=True,
        )
    with c3:
        st.metric("Aktive", sum(1 for row in clean_rows if row.get("active")))


__all__ = ["render_actor_registry_panel"]
