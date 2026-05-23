from __future__ import annotations

from typing import Any, Mapping, Sequence

import streamlit as st

from actor_registry import (
    ACTOR_TYPES,
    STRENGTH_LEVELS,
    actor_registry_to_csv,
    actor_registry_to_json,
    load_actor_registry,
    normalize_actor_row,
    parse_actor_registry_upload,
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

    upload = st.file_uploader(
        "Importer aktørregister CSV/JSON",
        type=["csv", "json", "txt"],
        key="actor_registry_import_v1863be",
        help="Kolonner: active, name, aliases, market, actor_type, strength, relevant_tickers, notes, links.",
    )
    if upload is not None:
        try:
            imported = parse_actor_registry_upload(upload.getvalue(), upload.name)
            if imported:
                by_key = {str(row.get("name") or row.get("aliases") or "").lower(): row for row in rows}
                for row in imported:
                    by_key[str(row.get("name") or row.get("aliases") or "").lower()] = row
                rows = list(by_key.values())
                st.success(f"Importerte {len(imported)} aktorer. Trykk Lagre aktørregister for aa lagre.")
            else:
                st.warning("Fant ingen aktorer i importfilen.")
        except Exception as exc:
            st.warning(f"Kunne ikke importere aktørregister: {exc}")

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
            "relevant_tickers": st.column_config.TextColumn("Tickere", help="Valgfritt. Skill tickere med komma eller semikolon."),
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
            data=actor_registry_to_json(clean_rows),
            file_name="aktorregister.json",
            mime="application/json",
            use_container_width=True,
        )
    with c3:
        st.download_button(
            "Last ned CSV",
            data=actor_registry_to_csv(clean_rows),
            file_name="aktorregister.csv",
            mime="text/csv",
            use_container_width=True,
        )
    st.caption(f"Aktive: {sum(1 for row in clean_rows if row.get('active'))}. Registeret overstyrer fallback-regler naar navn/alias matcher.")


__all__ = ["render_actor_registry_panel"]
