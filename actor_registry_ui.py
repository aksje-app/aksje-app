from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

import streamlit as st

from actor_registry import (
    ACTOR_ROLES,
    ACTOR_TYPES,
    STRENGTH_LEVELS,
    TRUST_LEVELS,
    actor_hit_stats,
    actor_registry_to_csv,
    actor_registry_to_json,
    actor_roles,
    load_actor_registry,
    match_actor_text,
    normalize_actor_row,
    parse_actor_registry_upload,
    save_actor_registry,
)


MARKET_OPTIONS = ["Alle", "Norge", "Sverige", "Danmark", "Finland", "USA", "Brasil", "Norden", "Global"]
EDITOR_ROWS_KEY = "actor_registry_editor_rows_v1863bi"
SORT_OPTIONS = {
    "Navn": "name",
    "Alias": "aliases",
    "Marked": "market",
    "Roller": "actor_roles",
    "Type": "actor_type",
    "Styrke": "strength",
    "Tillit": "trust_level",
    "Treff": "hit_count",
    "Sist funnet": "last_seen",
}


def _stable_row_id(row: Mapping[str, Any], index: int = 0) -> str:
    seed = "|".join(str(row.get(key) or "") for key in ("name", "aliases", "market", "actor_roles", "actor_type"))
    return "actor_" + hashlib.sha1(f"{seed}|{index}".encode("utf-8", errors="ignore")).hexdigest()[:16]


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


def _editor_row(row: Mapping[str, Any], index: int = 0) -> dict[str, Any]:
    out = normalize_actor_row(row)
    out["delete"] = bool(row.get("delete", False))
    out["_row_id"] = str(row.get("_row_id") or _stable_row_id(out, index))
    return out


def _with_row_ids(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [_editor_row(row, index) for index, row in enumerate(rows)]


def _blank_actor_row() -> dict[str, Any]:
    row = normalize_actor_row({
        "active": True,
        "name": "",
        "aliases": "",
        "market": "Alle",
        "actor_roles": "Bjellesau",
        "strength": "Normal",
        "trust_level": "Manuelt lagt inn",
        "relevant_tickers": "",
        "notes": "",
        "links": "",
    })
    row["delete"] = False
    row["_row_id"] = "new_" + hashlib.sha1(str(len(st.session_state.get(EDITOR_ROWS_KEY, []))).encode("utf-8")).hexdigest()[:16]
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
        st.session_state[EDITOR_ROWS_KEY] = _with_row_ids(load_actor_registry())
    return _with_row_ids(st.session_state.get(EDITOR_ROWS_KEY, []))


def _display_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    stats = actor_hit_stats(rows)
    out: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        item = _editor_row(row, index)
        hit = stats.get((item.get("name") or item.get("aliases") or "").strip().lower(), {})
        item["hit_count"] = int(hit.get("hit_count") or 0)
        item["last_seen"] = hit.get("last_seen") or ""
        item["hit_tickers"] = hit.get("tickers") or ""
        item["hit_markets"] = hit.get("markets") or ""
        out.append(item)
    return out


def _filter_rows(rows: Sequence[Mapping[str, Any]], query: str, active_only: bool) -> list[dict[str, Any]]:
    needle = str(query or "").strip().lower()
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if active_only and not row.get("active"):
            continue
        blob = " ".join(str(row.get(key) or "") for key in ("name", "aliases", "market", "actor_roles", "actor_type", "strength", "trust_level", "relevant_tickers", "notes", "links")).lower()
        if needle and needle not in blob:
            continue
        filtered.append(dict(row))
    return filtered


def _sort_rows(rows: Sequence[Mapping[str, Any]], sort_label: str, descending: bool) -> list[dict[str, Any]]:
    key = SORT_OPTIONS.get(sort_label, "name")

    def sort_value(row: Mapping[str, Any]) -> Any:
        value = row.get(key)
        if key == "hit_count":
            try:
                return int(value or 0)
            except Exception:
                return 0
        return str(value or "").lower()

    return sorted((dict(row) for row in rows), key=sort_value, reverse=descending)


def _merge_visible_edits(all_rows: Sequence[Mapping[str, Any]], edited_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    merged = [_editor_row(row, index) for index, row in enumerate(all_rows)]
    by_id = {row.get("_row_id"): idx for idx, row in enumerate(merged)}
    for raw in edited_rows:
        row = _editor_row(raw)
        row_id = row.get("_row_id")
        if row_id in by_id:
            merged[by_id[row_id]] = row
        else:
            merged.append(row)
    return merged


def _clean_for_save(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        normalize_actor_row(row)
        for row in rows
        if isinstance(row, Mapping) and not row.get("delete") and (str(row.get("name") or "").strip() or str(row.get("aliases") or "").strip())
    ]


def _alias_suggestions(name: str, aliases: str = "") -> list[str]:
    parts = [part for part in str(name or "").replace(",", " ").split() if len(part) > 1]
    suggestions: list[str] = []
    if name:
        suggestions.append(name.strip())
    if len(parts) >= 2:
        first, last = parts[0], parts[-1]
        suggestions.extend([last, f"{first} {last}", f"{last} Invest", f"{last} Holding", f"{last} Capital"])
    for suffix in ("Invest", "Investment", "Holding", "Capital", "Fond", "AS", "AB", "Ltd"):
        if name:
            suggestions.append(f"{name.strip()} {suffix}")
    existing = {alias.strip().lower() for alias in str(aliases or "").replace(",", ";").split(";") if alias.strip()}
    out: list[str] = []
    for suggestion in suggestions:
        clean = suggestion.strip()
        if clean and clean.lower() not in existing and clean.lower() not in {x.lower() for x in out}:
            out.append(clean)
    return out[:12]


def _find_similar(rows: Sequence[Mapping[str, Any]], text: str, current_row_id: str = "") -> list[dict[str, Any]]:
    words = {part.lower() for part in str(text or "").replace(";", " ").replace(",", " ").split() if len(part) >= 3}
    if not words:
        return []
    matches: list[dict[str, Any]] = []
    for row in rows:
        if current_row_id and row.get("_row_id") == current_row_id:
            continue
        blob = " ".join(str(row.get(key) or "") for key in ("name", "aliases")).lower()
        score = sum(1 for word in words if word in blob)
        if score:
            item = dict(row)
            item["match_score"] = score
            matches.append(item)
    return sorted(matches, key=lambda item: item.get("match_score", 0), reverse=True)[:8]


def _append_aliases(row: Mapping[str, Any], additions: Sequence[str]) -> dict[str, Any]:
    clean = normalize_actor_row(row)
    existing = [alias.strip() for alias in clean.get("aliases", "").split(";") if alias.strip()]
    for alias in additions:
        text = str(alias or "").strip()
        if text and text.lower() not in {item.lower() for item in existing}:
            existing.append(text)
    clean["aliases"] = "; ".join(existing)
    clean["_row_id"] = row.get("_row_id")
    clean["delete"] = bool(row.get("delete", False))
    return clean


def _update_row(all_rows: Sequence[Mapping[str, Any]], row_id: str, updates: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, raw in enumerate(all_rows):
        row = _editor_row(raw, index)
        if row.get("_row_id") == row_id:
            row.update(updates)
            row = _editor_row(row, index)
        out.append(row)
    return out


def render_actor_registry_panel() -> None:
    st.subheader("Aktørregister")
    st.caption(
        "Redigerbare navn og alias for bjellesauer, institusjoner og insider-watch. "
        "Registeret brukes i Alpha Radar/Early Warning til aa merke hvem som er hvem naar navn dukker opp i eier-, insider- eller nyhetsspor."
    )
    st.info("Lagres lokalt i appen. Navn og alias kan inngå i søkestrenger når du trykker Kjør, men registeret lastes ikke opp som egen database.")

    rows = _active_editor_rows()
    active_count = sum(1 for row in rows if row.get("active"))
    st.info(f"{len(rows)} aktorer i registeret, {active_count} aktive. Ingen nettverkskall kjores her.")

    upload = st.file_uploader(
        "Importer aktørregister CSV/JSON",
        type=["csv", "json", "txt"],
        key="actor_registry_import_v1863bi",
        help="Kolonner: active, name, aliases, market, actor_type, actor_roles, strength, trust_level, relevant_tickers, notes, links.",
    )
    if upload is not None:
        try:
            imported = parse_actor_registry_upload(upload.getvalue(), upload.name)
            if imported:
                by_key = {str(row.get("name") or row.get("aliases") or "").lower(): row for row in rows}
                for row in imported:
                    by_key[str(row.get("name") or row.get("aliases") or "").lower()] = row
                st.session_state[EDITOR_ROWS_KEY] = _with_row_ids(by_key.values())
                st.success(f"Importerte {len(imported)} aktorer. Trykk Lagre aktørregister for aa lagre.")
                st.rerun()
            else:
                st.warning("Fant ingen aktorer i importfilen.")
        except Exception as exc:
            st.warning(f"Kunne ikke importere aktørregister: {exc}")

    c_add, c_reload = st.columns([1, 1])
    with c_add:
        if st.button("Legg til aktør", key="actor_registry_add_v1863bi", use_container_width=True):
            st.session_state[EDITOR_ROWS_KEY] = rows + [_blank_actor_row()]
            st.rerun()
    with c_reload:
        if st.button("Last inn lagret register på nytt", key="actor_registry_reload_v1863bi", use_container_width=True):
            st.session_state[EDITOR_ROWS_KEY] = _with_row_ids(load_actor_registry())
            st.rerun()

    f1, f2, f3, f4 = st.columns([1.4, .9, .7, .7])
    with f1:
        search_text = st.text_input("Søk i registeret", key="actor_registry_search_v1863bi", placeholder="Navn, alias, ticker, marked, notat")
    with f2:
        sort_label = st.selectbox("Sorter etter", list(SORT_OPTIONS), key="actor_registry_sort_v1863bi")
    with f3:
        descending = st.checkbox("Synkende", value=sort_label == "Treff", key="actor_registry_sort_desc_v1863bi")
    with f4:
        active_only = st.checkbox("Bare aktive", value=False, key="actor_registry_active_only_v1863bi")

    visible = _sort_rows(_filter_rows(_display_rows(rows), search_text, active_only), sort_label, descending)
    st.caption(f"Viser {len(visible)} av {len(rows)} aktorer. Kolonnene kan også sorteres direkte i tabellen.")

    edited = st.data_editor(
        visible,
        key="actor_registry_editor_v1863bi",
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        column_order=[
            "delete", "active", "name", "aliases", "market", "actor_roles", "strength", "trust_level",
            "relevant_tickers", "hit_count", "last_seen", "hit_tickers", "notes", "links",
        ],
        column_config={
            "_row_id": None,
            "actor_type": None,
            "delete": st.column_config.CheckboxColumn("Slett"),
            "active": st.column_config.CheckboxColumn("Aktiv"),
            "name": st.column_config.TextColumn("Navn"),
            "aliases": st.column_config.TextColumn("Alias", help="Skill alias med komma eller semikolon."),
            "market": st.column_config.SelectboxColumn("Marked", options=MARKET_OPTIONS, help="Alle/Global matcher bredt; marked matcher suffix og valgt marked."),
            "actor_roles": st.column_config.TextColumn("Roller", help="Flere roller skilles med semikolon, f.eks. Bjellesau; Insider watch."),
            "strength": st.column_config.SelectboxColumn("Styrke", options=list(STRENGTH_LEVELS)),
            "trust_level": st.column_config.SelectboxColumn("Tillit", options=list(TRUST_LEVELS)),
            "relevant_tickers": st.column_config.TextColumn("Tickere", help="Valgfritt. Skill tickere med komma eller semikolon."),
            "hit_count": st.column_config.NumberColumn("Treff", disabled=True),
            "last_seen": st.column_config.TextColumn("Sist funnet", disabled=True),
            "hit_tickers": st.column_config.TextColumn("Treff-tickere", disabled=True),
            "notes": st.column_config.TextColumn("Notater"),
            "links": st.column_config.TextColumn("Lenker"),
        },
    )
    edited_raw = _raw_rows_from_editor(edited)
    rows = _merge_visible_edits(rows, edited_raw)
    st.session_state[EDITOR_ROWS_KEY] = rows

    if st.button("Slett valgte", key="actor_registry_delete_selected_v1863bi", use_container_width=True):
        delete_ids = {str(row.get("_row_id")) for row in edited_raw if row.get("delete")}
        st.session_state[EDITOR_ROWS_KEY] = [row for row in rows if str(row.get("_row_id")) not in delete_ids]
        st.rerun()

    clean_rows = _clean_for_save(rows)

    with st.expander("Hurtigrediger valgt aktør", expanded=False):
        options = {f"{row.get('name') or row.get('aliases') or '(uten navn)'} | {row.get('market')} | {row.get('_row_id')}": row for row in rows}
        selected_label = st.selectbox("Velg aktør", list(options), key="actor_registry_quick_actor_v1863bi") if options else ""
        selected = options.get(selected_label) if selected_label else None
        if selected:
            selected_id = str(selected.get("_row_id"))
            current_roles = actor_roles(selected)
            role_choices = st.multiselect("Roller for valgt aktør", list(ACTOR_ROLES), default=current_roles, key="actor_registry_quick_roles_v1863bi")
            q1, q2 = st.columns([1, 1])
            with q1:
                quick_strength = st.selectbox("Styrke", list(STRENGTH_LEVELS), index=list(STRENGTH_LEVELS).index(selected.get("strength") if selected.get("strength") in STRENGTH_LEVELS else "Normal"), key="actor_registry_quick_strength_v1863bi")
            with q2:
                quick_trust = st.selectbox("Tillit", list(TRUST_LEVELS), index=list(TRUST_LEVELS).index(selected.get("trust_level") if selected.get("trust_level") in TRUST_LEVELS else "Manuelt lagt inn"), key="actor_registry_quick_trust_v1863bi")
            alias_suggestions = _alias_suggestions(str(selected.get("name") or ""), str(selected.get("aliases") or ""))
            chosen_suggestions = st.multiselect("Alias-forslag", alias_suggestions, key="actor_registry_alias_suggestions_v1863bi")
            manual_alias = st.text_input("Nytt alias", key="actor_registry_manual_alias_v1863bi", placeholder="Legg til alias/navnevariant")
            c_role, c_alias = st.columns([1, 1])
            with c_role:
                if st.button("Oppdater roller/tillit", key="actor_registry_apply_roles_v1863bi", use_container_width=True):
                    st.session_state[EDITOR_ROWS_KEY] = _update_row(rows, selected_id, {
                        "actor_roles": "; ".join(role_choices or current_roles),
                        "strength": quick_strength,
                        "trust_level": quick_trust,
                    })
                    st.rerun()
            with c_alias:
                if st.button("Legg til alias", key="actor_registry_add_alias_v1863bi", use_container_width=True):
                    additions = list(chosen_suggestions)
                    if manual_alias.strip():
                        additions.append(manual_alias.strip())
                    updated_rows = []
                    for row in rows:
                        if str(row.get("_row_id")) == selected_id:
                            updated_rows.append(_append_aliases(row, additions))
                        else:
                            updated_rows.append(dict(row))
                    st.session_state[EDITOR_ROWS_KEY] = updated_rows
                    st.rerun()
            similar = _find_similar(rows, f"{selected.get('name')} {selected.get('aliases')}", selected_id)
            if similar:
                st.warning("Mulige duplikater/lignende aktører finnes allerede:")
                st.dataframe(
                    [{key: row.get(key) for key in ("name", "aliases", "market", "actor_roles", "match_score")} for row in similar],
                    use_container_width=True,
                    hide_index=True,
                )

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        if st.button("Lagre aktørregister", key="actor_registry_save_v1863bi", type="primary", use_container_width=True):
            for warning in _validate_rows(clean_rows):
                st.warning(warning)
            saved = save_actor_registry(clean_rows)
            st.session_state[EDITOR_ROWS_KEY] = _with_row_ids(clean_rows)
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
        test_text = st.text_area("Tekst som skal testes", key="actor_registry_test_text_v1863bi", height=120)
        t1, t2 = st.columns([1, 1])
        with t1:
            test_market = st.selectbox("Marked for test", MARKET_OPTIONS, key="actor_registry_test_market_v1863bi")
        with t2:
            test_ticker = st.text_input("Ticker for test", key="actor_registry_test_ticker_v1863bi")
        if test_text.strip():
            matches = match_actor_text(test_text, market=test_market, ticker=test_ticker, rows=clean_rows)
            if matches:
                st.dataframe(matches, use_container_width=True, hide_index=True)
            else:
                st.info("Ingen aktiv aktor/alias matchet teksten.")

    with st.expander("Trefflogg per aktør", expanded=False):
        stats = actor_hit_stats(clean_rows)
        hit_rows = []
        for row in clean_rows:
            key = (row.get("name") or row.get("aliases") or "").strip().lower()
            hit = stats.get(key, {})
            hit_rows.append({
                "Navn": row.get("name"),
                "Roller": row.get("actor_roles"),
                "Treff": hit.get("hit_count", 0),
                "Sist funnet": hit.get("last_seen", ""),
                "Tickere": hit.get("tickers", ""),
                "Markeder": hit.get("markets", ""),
                "Kilder": hit.get("sources", ""),
            })
        st.dataframe(hit_rows, use_container_width=True, hide_index=True)

    with st.expander("Unmatched Workbench", expanded=False):
        st.caption("Bruk denne naar radar/kilder viser navn som ikke matcher registeret. En linje blir en inaktiv ny aktor du kan redigere og aktivere.")
        pasted = st.text_area("Navn fra uavklarte funn", key="actor_registry_unmatched_paste_v1863bi", height=100)
        if st.button("Lag inaktive aktørrader fra tekst", key="actor_registry_unmatched_create_v1863bi", use_container_width=True):
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
                    "actor_roles": "Bjellesau",
                    "strength": "Normal",
                    "trust_level": "Usikker",
                    "notes": "Opprettet fra Unmatched Workbench. Kontroller alias/marked foer aktivering.",
                })))
            if additions:
                st.session_state[EDITOR_ROWS_KEY] = _with_row_ids(rows + additions)
                st.rerun()
            else:
                st.warning("Lim inn minst ett navn foer du lager rader.")

    st.caption(f"Aktive: {sum(1 for row in clean_rows if row.get('active'))}. En aktør kan ha flere roller, f.eks. Bjellesau; Insider watch, uten dobbeltregistrering.")


__all__ = ["render_actor_registry_panel"]
