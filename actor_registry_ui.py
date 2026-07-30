from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

import streamlit as st

from actor_registry import (
    ACTOR_ROLES,
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
EDITOR_ROWS_KEY = "actor_registry_editor_rows_v1863bj"
NEW_ACTOR_OPEN_KEY = "actor_registry_new_actor_open_v1863bj"
HIT_STATS_KEY = "actor_registry_hit_stats_v1863bj"
SORT_OPTIONS = {
    "Navn": "name",
    "Alias": "aliases",
    "Marked": "market",
    "Roller": "actor_roles",
    "Styrke": "strength",
    "Tillit": "trust_level",
    "Treff": "hit_count",
    "Sist funnet": "last_seen",
}


def _stable_row_id(row: Mapping[str, Any], index: int = 0) -> str:
    seed = "|".join(str(row.get(key) or "") for key in ("name", "aliases", "market", "actor_roles", "actor_type"))
    return "actor_" + hashlib.sha1(f"{seed}|{index}".encode("utf-8", errors="ignore")).hexdigest()[:16]


def _editor_row(row: Mapping[str, Any], index: int = 0) -> dict[str, Any]:
    out = normalize_actor_row(row)
    out["_row_id"] = str(row.get("_row_id") or _stable_row_id(out, index))
    return out


def _with_row_ids(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [_editor_row(row, index) for index, row in enumerate(rows)]


def _active_editor_rows() -> list[dict[str, Any]]:
    if EDITOR_ROWS_KEY not in st.session_state:
        st.session_state[EDITOR_ROWS_KEY] = _with_row_ids(load_actor_registry())
    return [_editor_row(row, index) for index, row in enumerate(st.session_state.get(EDITOR_ROWS_KEY, []))]


def _clean_for_save(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        normalize_actor_row(row)
        for row in rows
        if isinstance(row, Mapping) and (str(row.get("name") or "").strip() or str(row.get("aliases") or "").strip())
    ]


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


def _display_rows(rows: Sequence[Mapping[str, Any]], stats: Mapping[str, Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    stats = stats or {}
    for index, row in enumerate(rows):
        item = _editor_row(row, index)
        hit = stats.get((item.get("name") or item.get("aliases") or "").strip().lower(), {})
        item["hit_count"] = int(hit.get("hit_count") or 0) if hit else 0
        item["last_seen"] = hit.get("last_seen") or "" if hit else ""
        item["hit_tickers"] = hit.get("tickers") or "" if hit else ""
        out.append(item)
    return out


def _filter_rows(rows: Sequence[Mapping[str, Any]], query: str, active_only: bool) -> list[dict[str, Any]]:
    needle = str(query or "").strip().lower()
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if active_only and not row.get("active"):
            continue
        blob = " ".join(str(row.get(key) or "") for key in (
            "name",
            "aliases",
            "market",
            "actor_roles",
            "actor_type",
            "strength",
            "trust_level",
            "relevant_tickers",
            "notes",
            "links",
        )).lower()
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


def _option_index(options: Sequence[str], value: Any, default: int = 0) -> int:
    try:
        return list(options).index(str(value))
    except Exception:
        return default


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


def _append_aliases(aliases: str, additions: Sequence[str]) -> str:
    existing = [alias.strip() for alias in str(aliases or "").replace(",", ";").split(";") if alias.strip()]
    for alias in additions:
        text = str(alias or "").strip()
        if text and text.lower() not in {item.lower() for item in existing}:
            existing.append(text)
    return "; ".join(existing)


def _row_label(row: Mapping[str, Any]) -> str:
    return f"{row.get('name') or row.get('aliases') or '(uten navn)'} | {row.get('market')} | {row.get('actor_roles')} | {row.get('_row_id')}"


def _replace_row(rows: Sequence[Mapping[str, Any]], row_id: str, replacement: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if str(row.get("_row_id")) == row_id:
            updated = _editor_row(replacement, index)
            updated["_row_id"] = row_id
            out.append(updated)
        else:
            out.append(_editor_row(row, index))
    return out


def _actor_form(prefix: str, row: Mapping[str, Any] | None = None) -> dict[str, Any]:
    clean = _editor_row(row or {})
    active = st.checkbox("Aktiv", value=bool(clean.get("active", True)), key=f"{prefix}_active")
    name = st.text_input("Navn", value=str(clean.get("name") or ""), key=f"{prefix}_name")
    aliases = st.text_area("Alias/navnevarianter", value=str(clean.get("aliases") or ""), key=f"{prefix}_aliases", height=80)
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        market = st.selectbox("Marked", MARKET_OPTIONS, index=_option_index(MARKET_OPTIONS, clean.get("market"), 0), key=f"{prefix}_market")
    with c2:
        roles = st.multiselect("Roller", list(ACTOR_ROLES), default=actor_roles(clean), key=f"{prefix}_roles")
    with c3:
        strength = st.selectbox("Styrke", list(STRENGTH_LEVELS), index=_option_index(STRENGTH_LEVELS, clean.get("strength"), 1), key=f"{prefix}_strength")
    trust_level = st.selectbox("Tillit", list(TRUST_LEVELS), index=_option_index(TRUST_LEVELS, clean.get("trust_level"), 1), key=f"{prefix}_trust")
    relevant_tickers = st.text_input("Relevante tickere/selskaper", value=str(clean.get("relevant_tickers") or ""), key=f"{prefix}_tickers")
    suggestions = _alias_suggestions(name, aliases)
    chosen_suggestions = st.multiselect("Raske alias-forslag", suggestions, key=f"{prefix}_alias_suggestions")
    manual_alias = st.text_input("Legg til alias", key=f"{prefix}_manual_alias", placeholder="Person, fond, holdingselskap eller forkortelse")
    notes = st.text_area("Notater", value=str(clean.get("notes") or ""), key=f"{prefix}_notes", height=70)
    links = st.text_input("Kildelenker", value=str(clean.get("links") or ""), key=f"{prefix}_links")
    additions = list(chosen_suggestions)
    if manual_alias.strip():
        additions.append(manual_alias.strip())
    aliases = _append_aliases(aliases, additions)
    return normalize_actor_row({
        "active": active,
        "name": name,
        "aliases": aliases,
        "market": market,
        "actor_roles": "; ".join(roles or ["Bjellesau"]),
        "strength": strength,
        "trust_level": trust_level,
        "relevant_tickers": relevant_tickers,
        "notes": notes,
        "links": links,
    })


def render_actor_registry_panel() -> None:
    st.subheader("Aktørregister")
    st.caption(
        "Redigerbare navn og alias for bjellesauer, institusjoner og insider-watch. "
        "Registeret brukes i Alpha Radar/Early Warning når navn dukker opp i eier-, insider- eller nyhetsspor."
    )
    st.info("Lagres lokalt i appen. Navn og alias kan inngå i søkestrenger når du trykker Kjør, men registeret lastes ikke opp som egen database.")

    rows = _active_editor_rows()
    active_count = sum(1 for row in rows if row.get("active"))
    st.info(f"{len(rows)} aktører i registeret, {active_count} aktive. Ingen nettverkskall kjøres her.")

    upload = st.file_uploader(
        "Importer aktørregister CSV/JSON",
        type=["csv", "json", "txt"],
        key="actor_registry_import_v1863bj",
        help="Kolonner: active, name, aliases, market, actor_roles, strength, trust_level, relevant_tickers, notes, links.",
    )
    if upload is not None:
        try:
            imported = parse_actor_registry_upload(upload.getvalue(), upload.name)
            if imported:
                by_key = {str(row.get("name") or row.get("aliases") or "").lower(): row for row in rows}
                for row in imported:
                    by_key[str(row.get("name") or row.get("aliases") or "").lower()] = row
                st.session_state[EDITOR_ROWS_KEY] = _with_row_ids(by_key.values())
                st.success(f"Importerte {len(imported)} aktører. Trykk Lagre aktørregister for å lagre.")
                st.rerun()
            else:
                st.warning("Fant ingen aktører i importfilen.")
        except Exception as exc:
            st.warning(f"Kunne ikke importere aktørregister: {exc}")

    c_add, c_reload = st.columns([1, 1])
    with c_add:
        if st.button("Legg til aktør", key="actor_registry_add_v1863bj", width="stretch"):
            st.session_state[NEW_ACTOR_OPEN_KEY] = True
    with c_reload:
        if st.button("Last inn lagret register på nytt", key="actor_registry_reload_v1863bj", width="stretch"):
            st.session_state[EDITOR_ROWS_KEY] = _with_row_ids(load_actor_registry())
            st.rerun()

    if st.session_state.get(NEW_ACTOR_OPEN_KEY):
        with st.form("actor_registry_new_actor_form_v1863bj"):
            st.markdown("**Ny aktør**")
            new_row = _actor_form("actor_registry_new_v1863bj", {"active": True, "market": "Alle", "actor_roles": "Bjellesau", "strength": "Normal", "trust_level": "Manuelt lagt inn"})
            duplicates = _find_similar(rows, f"{new_row.get('name')} {new_row.get('aliases')}")
            if duplicates:
                st.warning("Mulige duplikater finnes allerede:")
                st.dataframe([{key: row.get(key) for key in ("name", "aliases", "market", "actor_roles", "match_score")} for row in duplicates], width="stretch", hide_index=True)
            s1, s2 = st.columns([1, 1])
            with s1:
                create_new = st.form_submit_button("Opprett aktør", width="stretch")
            with s2:
                cancel_new = st.form_submit_button("Avbryt", width="stretch")
        if create_new:
            if not (new_row.get("name") or new_row.get("aliases")):
                st.warning("Navn eller alias må fylles ut.")
            else:
                st.session_state[EDITOR_ROWS_KEY] = _with_row_ids(rows + [new_row])
                st.session_state[NEW_ACTOR_OPEN_KEY] = False
                st.rerun()
        if cancel_new:
            st.session_state[NEW_ACTOR_OPEN_KEY] = False
            st.rerun()

    f1, f2, f3, f4 = st.columns([1.4, .9, .7, .7])
    with f1:
        search_text = st.text_input("Søk i registeret", key="actor_registry_search_v1863bj", placeholder="Navn, alias, ticker, marked, notat")
    with f2:
        sort_label = st.selectbox("Sorter etter", list(SORT_OPTIONS), key="actor_registry_sort_v1863bj")
    with f3:
        descending = st.checkbox("Synkende", value=sort_label == "Treff", key="actor_registry_sort_desc_v1863bj")
    with f4:
        active_only = st.checkbox("Bare aktive", value=False, key="actor_registry_active_only_v1863bj")

    hit_stats = st.session_state.get(HIT_STATS_KEY) if isinstance(st.session_state.get(HIT_STATS_KEY), Mapping) else None
    visible = _sort_rows(_filter_rows(_display_rows(rows, hit_stats), search_text, active_only), sort_label, descending)
    st.caption(f"Viser {len(visible)} av {len(rows)} aktører. Tabellen er lettvisning; redigering skjer i skjemaet under.")
    st.dataframe(
        visible,
        key="actor_registry_table_v1863bj",
        width="stretch",
        hide_index=True,
        column_order=["active", "name", "aliases", "market", "actor_roles", "strength", "trust_level", "relevant_tickers", "hit_count", "last_seen", "hit_tickers", "notes", "links"],
        column_config={
            "_row_id": None,
            "actor_type": None,
            "active": st.column_config.CheckboxColumn("Aktiv"),
            "name": st.column_config.TextColumn("Navn"),
            "aliases": st.column_config.TextColumn("Alias"),
            "market": st.column_config.TextColumn("Marked"),
            "actor_roles": st.column_config.TextColumn("Roller"),
            "strength": st.column_config.TextColumn("Styrke"),
            "trust_level": st.column_config.TextColumn("Tillit"),
            "relevant_tickers": st.column_config.TextColumn("Tickere"),
            "hit_count": st.column_config.NumberColumn("Treff"),
            "last_seen": st.column_config.TextColumn("Sist funnet"),
            "hit_tickers": st.column_config.TextColumn("Treff-tickere"),
            "notes": st.column_config.TextColumn("Notater"),
            "links": st.column_config.TextColumn("Lenker"),
        },
    )

    if rows:
        labels = [_row_label(row) for row in rows]
        selected_label = st.selectbox("Velg aktør å redigere", labels, key="actor_registry_selected_actor_v1863bj")
        selected = rows[labels.index(selected_label)]
        selected_id = str(selected.get("_row_id"))
        with st.form(f"actor_registry_edit_form_v1863bj_{selected_id}"):
            st.markdown("**Rediger valgt aktør**")
            updated = _actor_form(f"actor_registry_edit_v1863bj_{selected_id}", selected)
            similar = _find_similar(rows, f"{updated.get('name')} {updated.get('aliases')}", selected_id)
            if similar:
                st.warning("Mulige duplikater/lignende aktører finnes allerede:")
                st.dataframe([{key: row.get(key) for key in ("name", "aliases", "market", "actor_roles", "match_score")} for row in similar], width="stretch", hide_index=True)
            save_selected = st.form_submit_button("Lagre valgt aktør", width="stretch")
        if save_selected:
            st.session_state[EDITOR_ROWS_KEY] = _replace_row(rows, selected_id, updated)
            st.rerun()

        delete_labels = st.multiselect("Velg aktører for sletting", labels, key="actor_registry_delete_choices_v1863bj")
        if st.button("Slett valgte", key="actor_registry_delete_selected_v1863bj", width="stretch"):
            delete_ids = {label.split("|")[-1].strip() for label in delete_labels}
            if delete_ids:
                st.session_state[EDITOR_ROWS_KEY] = [row for row in rows if str(row.get("_row_id")) not in delete_ids]
                st.rerun()
            else:
                st.warning("Velg minst en aktør før sletting.")

    clean_rows = _clean_for_save(rows)
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        if st.button("Lagre aktørregister", key="actor_registry_save_v1863bj", type="primary", width="stretch"):
            for warning in _validate_rows(clean_rows):
                st.warning(warning)
            saved = save_actor_registry(clean_rows)
            st.session_state[EDITOR_ROWS_KEY] = _with_row_ids(clean_rows)
            try:
                from alpha_radar_enrichment import reset_bjellesau_watchlist_cache

                reset_bjellesau_watchlist_cache()
            except Exception:
                pass
            st.success(f"Lagret {saved} aktører.")
    with c2:
        st.download_button(
            "Last ned JSON",
            data=actor_registry_to_json(clean_rows),
            file_name="aktorregister.json",
            mime="application/json",
            width="stretch",
        )
    with c3:
        st.download_button(
            "Last ned CSV",
            data=actor_registry_to_csv(clean_rows),
            file_name="aktorregister.csv",
            mime="text/csv",
            width="stretch",
        )

    with st.expander("Test aktør mot tekst", expanded=False):
        st.caption("Lim inn en nyhet, børsmelding eller insidertekst for å se hvilke aktive alias som matcher.")
        test_text = st.text_area("Tekst som skal testes", key="actor_registry_test_text_v1863bj", height=120)
        t1, t2 = st.columns([1, 1])
        with t1:
            test_market = st.selectbox("Marked for test", MARKET_OPTIONS, key="actor_registry_test_market_v1863bj")
        with t2:
            test_ticker = st.text_input("Ticker for test", key="actor_registry_test_ticker_v1863bj")
        if test_text.strip():
            matches = match_actor_text(test_text, market=test_market, ticker=test_ticker, rows=clean_rows)
            if matches:
                st.dataframe(matches, width="stretch", hide_index=True)
            else:
                st.info("Ingen aktiv aktør/alias matchet teksten.")

    with st.expander("Trefflogg per aktør", expanded=False):
        st.caption("Hentes bare når du trykker knappen, slik at menyvalg ikke blir tunge.")
        if st.button("Oppdater trefflogg", key="actor_registry_refresh_hits_v1863bj", width="stretch"):
            st.session_state[HIT_STATS_KEY] = actor_hit_stats(clean_rows)
            st.rerun()
        stats = st.session_state.get(HIT_STATS_KEY) if isinstance(st.session_state.get(HIT_STATS_KEY), Mapping) else {}
        if stats:
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
            st.dataframe(hit_rows, width="stretch", hide_index=True)
        else:
            st.info("Trykk Oppdater trefflogg for å hente lokale treff.")

    with st.expander("Unmatched Workbench", expanded=False):
        st.caption("Bruk denne når radar/kilder viser navn som ikke matcher registeret. En linje blir en inaktiv ny aktør du kan redigere og aktivere.")
        pasted = st.text_area("Navn fra uavklarte funn", key="actor_registry_unmatched_paste_v1863bj", height=100)
        if st.button("Lag inaktive aktørrader fra tekst", key="actor_registry_unmatched_create_v1863bj", width="stretch"):
            additions = []
            for line in pasted.splitlines():
                name = line.strip(" -;\t")
                if not name:
                    continue
                additions.append(normalize_actor_row({
                    "active": False,
                    "name": name,
                    "aliases": name,
                    "market": "Alle",
                    "actor_roles": "Bjellesau",
                    "strength": "Normal",
                    "trust_level": "Usikker",
                    "notes": "Opprettet fra Unmatched Workbench. Kontroller alias/marked før aktivering.",
                }))
            if additions:
                st.session_state[EDITOR_ROWS_KEY] = _with_row_ids(rows + additions)
                st.rerun()
            else:
                st.warning("Lim inn minst ett navn før du lager rader.")

    st.caption(f"Aktive: {sum(1 for row in clean_rows if row.get('active'))}. En aktør kan ha flere roller, f.eks. Bjellesau + Insider watch, uten dobbeltregistrering.")


__all__ = ["render_actor_registry_panel"]
