from __future__ import annotations

from typing import Any, Mapping, Sequence

import streamlit as st

from actor_registry import (
    ACTOR_TYPES,
    STRENGTH_LEVELS,
    actor_registry_to_csv,
    actor_registry_to_json,
    load_actor_registry,
    match_actor_text,
    normalize_actor_row,
    parse_actor_registry_upload,
    save_actor_registry,
)


MARKET_OPTIONS = ["Alle", "Norge", "Sverige", "Danmark", "Finland", "USA", "Brasil", "Norden", "Global"]
EDITOR_ROWS_KEY = "actor_registry_editor_rows_v1863bh"


def _raw_rows_from_editor(value: Any) -> list[dict[str, Any]]:
    if hasattr(value, "to_dict"):
        try:
            records = value.to_dict("records")
            return [dict(row) for row in records if isinstance(row, Mapping)]
        except Exception:
            pass
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [dict(row) for row in value if isinstance(row, Mapping)]
    return []


def _rows_from_editor(value: Any) -> list[dict[str, Any]]:
    return [normalize_actor_row(row) for row in _raw_rows_from_editor(value)]


def _editor_row(row: Mapping[str, Any]) -> dict[str, Any]:
    out = normalize_actor_row(row)
    out["delete"] = bool(row.get("delete", False))
    return out


def _blank_actor_row() -> dict[str, Any]:
    row = normalize_actor_row({
        "active": True,
        "name": "",
        "aliases": "",
        "market": "Alle",
        "actor_type": "Bjellesau",
        "strength": "Normal",
        "relevant_tickers": "",
        "notes": "",
        "links": "",
    })
    row["delete"] = False
    return row


def _validate_rows(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    warnings: list[str] = []
    seen: set[str] = set()
    for row in rows:
        clean = normalize_actor_row(row)
        key = (clean.get("name") or clean.get("aliases") or "").strip().lower()
        if not key:
            warnings.append("Rader uten navn eller alias blir ikke lagret.")
            continue
        if key in seen:
            warnings.append(f"Duplikat i aktørregisteret: {clean.get('name') or clean.get('aliases')}")
        seen.add(key)
    return warnings[:5]


def _active_editor_rows() -> list[dict[str, Any]]:
    if EDITOR_ROWS_KEY not in st.session_state:
        st.session_state[EDITOR_ROWS_KEY] = [_editor_row(row) for row in load_actor_registry()]
    return [_editor_row(row) for row in st.session_state.get(EDITOR_ROWS_KEY, [])]


def render_actor_registry_panel() -> None:
    st.subheader("Aktørregister")
    st.caption(
        "Redigerbare navn og alias for bjellesauer, institusjoner og insider-watch. "
        "Registeret brukes i Alpha Radar/Early Warning til aa merke hvem som er hvem naar navn dukker opp i eier-, insider- eller nyhetsspor."
    )
    rows = _active_editor_rows()
    active_count = sum(1 for row in rows if row.get("active"))
    st.info(f"{len(rows)} aktorer i registeret, {active_count} aktive. Ingen nettverkskall kjores her.")

    upload = st.file_uploader(
        "Importer aktørregister CSV/JSON",
        type=["csv", "json", "txt"],
        key="actor_registry_import_v1863bh",
        help="Kolonner: active, name, aliases, market, actor_type, strength, relevant_tickers, notes, links.",
    )
    if upload is not None:
        try:
            imported = parse_actor_registry_upload(upload.getvalue(), upload.name)
            if imported:
                by_key = {str(row.get("name") or row.get("aliases") or "").lower(): row for row in rows}
                for row in imported:
                    by_key[str(row.get("name") or row.get("aliases") or "").lower()] = row
                st.session_state[EDITOR_ROWS_KEY] = [_editor_row(row) for row in by_key.values()]
                st.success(f"Importerte {len(imported)} aktorer. Trykk Lagre aktørregister for aa lagre.")
                st.rerun()
            else:
                st.warning("Fant ingen aktorer i importfilen.")
        except Exception as exc:
            st.warning(f"Kunne ikke importere aktørregister: {exc}")

    c_add, c_reload = st.columns([1, 1])
    with c_add:
        if st.button("Legg til aktør", key="actor_registry_add_v1863bh", use_container_width=True):
            st.session_state[EDITOR_ROWS_KEY] = rows + [_blank_actor_row()]
            st.rerun()
    with c_reload:
        if st.button("Last inn lagret register på nytt", key="actor_registry_reload_v1863bh", use_container_width=True):
            st.session_state[EDITOR_ROWS_KEY] = [_editor_row(row) for row in load_actor_registry()]
            st.rerun()

    edited = st.data_editor(
        rows,
        key="actor_registry_editor_v1863bh",
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "delete": st.column_config.CheckboxColumn("Slett"),
            "active": st.column_config.CheckboxColumn("Aktiv"),
            "name": st.column_config.TextColumn("Navn"),
            "aliases": st.column_config.TextColumn("Alias", help="Skill alias med komma eller semikolon."),
            "market": st.column_config.SelectboxColumn("Marked", options=MARKET_OPTIONS, help="Alle/Global matcher bredt; marked matcher suffix og valgt marked."),
            "actor_type": st.column_config.SelectboxColumn("Type", options=list(ACTOR_TYPES)),
            "strength": st.column_config.SelectboxColumn("Styrke", options=list(STRENGTH_LEVELS)),
            "relevant_tickers": st.column_config.TextColumn("Tickere", help="Valgfritt. Skill tickere med komma eller semikolon."),
            "notes": st.column_config.TextColumn("Notater"),
            "links": st.column_config.TextColumn("Lenker"),
        },
    )
    edited_raw = _raw_rows_from_editor(edited)
    if st.button("Slett valgte", key="actor_registry_delete_selected_v1863bh", use_container_width=True):
        st.session_state[EDITOR_ROWS_KEY] = [_editor_row(row) for row in edited_raw if not row.get("delete")]
        st.rerun()

    clean_rows = [row for row, raw in zip(_rows_from_editor(edited), edited_raw) if not raw.get("delete")]

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        if st.button("Lagre aktørregister", key="actor_registry_save_v1863bh", type="primary", use_container_width=True):
            for warning in _validate_rows(clean_rows):
                st.warning(warning)
            saved = save_actor_registry(clean_rows)
            st.session_state[EDITOR_ROWS_KEY] = [_editor_row(row) for row in clean_rows]
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

    with st.expander("Test aktør mot tekst", expanded=False):
        st.caption("Lim inn en nyhet, børsmelding eller insidertekst for aa se hvilke aktive alias som matcher.")
        test_text = st.text_area("Tekst som skal testes", key="actor_registry_test_text_v1863bh", height=120)
        t1, t2 = st.columns([1, 1])
        with t1:
            test_market = st.selectbox("Marked for test", MARKET_OPTIONS, key="actor_registry_test_market_v1863bh")
        with t2:
            test_ticker = st.text_input("Ticker for test", key="actor_registry_test_ticker_v1863bh")
        if test_text.strip():
            matches = match_actor_text(test_text, market=test_market, ticker=test_ticker, rows=clean_rows)
            if matches:
                st.dataframe(matches, use_container_width=True, hide_index=True)
            else:
                st.info("Ingen aktiv aktor/alias matchet teksten.")

    with st.expander("Unmatched Workbench", expanded=False):
        st.caption("Bruk denne naar radar/kilder viser navn som ikke matcher registeret. En linje blir en inaktiv ny aktor du kan redigere og aktivere.")
        pasted = st.text_area("Navn fra uavklarte funn", key="actor_registry_unmatched_paste_v1863bh", height=100)
        if st.button("Lag inaktive aktørrader fra tekst", key="actor_registry_unmatched_create_v1863bh", use_container_width=True):
            additions = []
            for line in pasted.splitlines():
                name = line.strip(" -;\t")
                if not name:
                    continue
                additions.append(_editor_row(normalize_actor_row({
                    "active": False,
                    "name": name,
                    "aliases": name,
                    "market": "Alle",
                    "actor_type": "Bjellesau",
                    "strength": "Normal",
                    "notes": "Opprettet fra Unmatched Workbench. Kontroller alias/marked foer aktivering.",
                })))
            if additions:
                st.session_state[EDITOR_ROWS_KEY] = [_editor_row(row) for row in clean_rows] + additions
                st.rerun()
            else:
                st.warning("Lim inn minst ett navn foer du lager rader.")

    st.caption(f"Aktive: {sum(1 for row in clean_rows if row.get('active'))}. Registeret overstyrer fallback-regler naar navn/alias matcher.")


__all__ = ["render_actor_registry_panel"]
