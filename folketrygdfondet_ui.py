from __future__ import annotations

import streamlit as st

from folketrygdfondet import (
    annotate_folketrygdfondet_holdings,
    build_folketrygdfondet_overlay,
    folketrygdfondet_display_rows,
    load_folketrygdfondet_overlay,
    read_folketrygdfondet_xls_bytes,
    save_folketrygdfondet_overlay,
)


def render_folketrygdfondet_panel() -> None:
    st.subheader("Folketrygdfondet")
    st.caption(
        "Importer Folketrygdfondet-beholdninger fra .xls/.xlsx. Dataene lagres som institusjonelt eier-overlay som senere tester kan bruke ved behov, "
        "ikke som raa regneark gjennom hele Test 1-10-flyten."
    )

    uploaded = st.file_uploader(
        "Importer Folketrygdfondet XLS",
        type=["xls", "xlsx"],
        key="folketrygdfondet_xls_upload_v1864k",
    )

    saved_overlay = load_folketrygdfondet_overlay()
    st.metric("Lagret overlay", f"{len(saved_overlay)} tickere")

    if not uploaded:
        st.info("Last opp Folketrygdfondet XLS for aa bygge/oppdatere overlay. Ingen import kjoeres foer du laster opp fil.")
        return

    try:
        rows = read_folketrygdfondet_xls_bytes(uploaded.getvalue(), uploaded.name)
    except Exception as exc:
        st.warning(str(exc))
        return

    annotated = annotate_folketrygdfondet_holdings(rows)
    overlay = build_folketrygdfondet_overlay(annotated)
    matched = sum(1 for row in annotated if row.get("matched_ticker"))

    m1, m2, m3 = st.columns(3)
    m1.metric("Input Folketrygdfondet", f"{len(rows)} rader")
    m2.metric("Ticker-match", f"{matched}")
    m3.metric("Overlay til tester", f"{len(overlay)} tickere")

    st.dataframe(folketrygdfondet_display_rows(annotated), use_container_width=True, hide_index=True)

    if st.button(
        "Lagre Folketrygdfondet-overlay",
        key="folketrygdfondet_save_overlay_v1864k",
        type="primary",
        use_container_width=True,
        disabled=not overlay,
    ):
        saved = save_folketrygdfondet_overlay(overlay)
        st.success(f"Lagret Folketrygdfondet-overlay for {saved} tickere.")


__all__ = ["render_folketrygdfondet_panel"]
