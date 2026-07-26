"""Strategy Lab workspace for v19.10.0."""
from __future__ import annotations

from typing import Any
import pandas as pd

from services.strategy_lab_service import StrategyLabError


def _actor(app_context: Any) -> str:
    user = getattr(app_context, "user", None)
    if isinstance(user, dict):
        return str(user.get("username") or user.get("email") or user.get("name") or "user")
    return str(getattr(user, "username", None) or getattr(user, "email", None) or user or "user")


def render_strategy_lab(app_context: Any) -> None:
    st = app_context["st"]
    lab = app_context.services.strategy_lab
    registry = app_context.services.strategy_registry
    actor = _actor(app_context)
    registry.ensure_defaults()
    lab.ensure_default_quality_experiment()
    experiments = lab.recent_experiments()
    runs = lab.recent_runs()
    approvals = lab.recent_approvals()

    st.markdown("### \U0001f9ea Strategy Lab")
    st.caption(
        "Sammenlign produksjonsbenchmark og skrivebeskyttede challengere p\u00e5 de samme snapshotene. "
        "Lab-kj\u00f8ringer kan ikke handle, endre produksjonsbinding eller promotere en strategi automatisk."
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Eksperimenter", len(experiments))
    c2.metric("Lab-kj\u00f8ringer", len(runs))
    c3.metric("Godkjenninger", sum(1 for row in approvals if str(row.get("status") or "").startswith("APPROVED")))
    c4.metric("Automatisk promotering", "Av")

    versions = registry.list_versions()
    baselines = [row for row in versions if row.get("status") == "PRODUCTION"]
    challengers = [row for row in versions if row.get("status") in {"SHADOW", "CHALLENGER"}]
    baseline_labels = {f"{row.get('display_name')} @ {row.get('strategy_version')}": row.get("version_id") for row in baselines}
    challenger_labels = {f"{row.get('display_name')} @ {row.get('strategy_version')}": row.get("version_id") for row in challengers}

    with st.expander("Opprett eksperiment", expanded=False):
        if not baseline_labels or not challenger_labels:
            st.warning("Strategy Lab trenger minst \u00e9n produksjonsbaseline og \u00e9n aktiv challenger.")
        else:
            with st.form("strategy_lab_create_v19100"):
                name = st.text_input("Navn", value="Technical Quality Challenger test")
                hypothesis = st.text_area("Hypotese", value="Rikere kvalitetsdata skal redusere svake innganger uten \u00e5 endre produksjonsbenchmarken.")
                baseline_label = st.selectbox("Produksjonsbaseline", list(baseline_labels))
                selected_challengers = st.multiselect("Challengere", list(challenger_labels), default=[next(iter(challenger_labels))])
                mode = st.selectbox("Testmodus", ["WALK_FORWARD", "SNAPSHOT_REPLAY"])
                train_ratio = st.slider("Treningsandel", 0.50, 0.90, 0.70, 0.05)
                submitted = st.form_submit_button("Opprett Strategy Lab-eksperiment")
            if submitted:
                try:
                    lab.create_experiment(
                        name=name,
                        hypothesis=hypothesis,
                        baseline_version_id=baseline_labels[baseline_label],
                        challenger_version_ids=[challenger_labels[label] for label in selected_challengers],
                        mode=mode,
                        train_ratio=train_ratio,
                        actor=actor,
                    )
                    st.success("Eksperiment opprettet. Ingen produksjonsbinding er endret.")
                    st.rerun()
                except StrategyLabError as exc:
                    st.error(str(exc))

    experiments = lab.recent_experiments()
    if experiments:
        display = [{
            "Eksperiment": row.get("name"),
            "Status": row.get("status"),
            "Baseline": row.get("baseline_version_id"),
            "Challengere": ", ".join(row.get("challenger_version_ids") or []),
            "Modus": row.get("mode"),
            "Siste kj\u00f8ring": row.get("latest_lab_run_id") or "-",
            "Produksjon endret": "Nei",
            "Oppdatert": row.get("updated_at"),
        } for row in experiments]
        st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)

        labels = {f"{row.get('name')} | {row.get('status')} | {row.get('experiment_id')}": row for row in experiments}
        selected_label = st.selectbox("Velg eksperiment", list(labels), key="strategy_lab_selected_v19100")
        selected = labels[selected_label]
        r1, r2 = st.columns(2)
        snapshot_count = r1.number_input("Bruk siste antall snapshots", min_value=1, max_value=500, value=30, step=1)
        if r2.button("Kj\u00f8r skrivebeskyttet replay", key="strategy_lab_run_v19100"):
            try:
                snapshots = sorted(app_context.services.repositories.market_snapshots.list(), key=lambda row: str(row.get("captured_at") or ""))
                snapshot_ids = [row.get("snapshot_id") for row in snapshots[-int(snapshot_count):] if row.get("snapshot_id")]
                result = lab.run_experiment(selected["experiment_id"], snapshot_ids=snapshot_ids, actor=actor)
                st.success(f"Lab-kj\u00f8ring fullf\u00f8rt: {result.get('decision_count')} beslutninger, {result.get('error_count')} feil.")
                st.rerun()
            except StrategyLabError as exc:
                st.error(str(exc))

        latest_run_id = selected.get("latest_lab_run_id")
        latest_run = next((row for row in runs if row.get("lab_run_id") == latest_run_id), None)
        if latest_run:
            st.markdown("#### Sammenligningsresultat")
            metrics = list(latest_run.get("metrics") or [])
            if metrics:
                st.dataframe(pd.DataFrame(metrics), use_container_width=True, hide_index=True)
            split = dict(latest_run.get("split") or {})
            st.caption(
                f"Tidsordnet split: {split.get('train_snapshots', 0)} trening / "
                f"{split.get('validation_snapshots', 0)} validering. Utf\u00f8relse og produksjonsp\u00e5virkning er deaktivert."
            )

        with st.expander("Manuell vurdering, godkjenning og rollback", expanded=False):
            reason = st.text_area("Begrunnelse", key="strategy_lab_review_reason_v19100")
            a1, a2 = st.columns(2)
            if a1.button("Send til vurdering", key="strategy_lab_review_v19100"):
                try:
                    lab.submit_review(selected["experiment_id"], actor=actor, reason=reason)
                    st.success("Eksperiment sendt til manuell vurdering.")
                    st.rerun()
                except StrategyLabError as exc:
                    st.error(str(exc))
            confirmation = a2.text_input("Skriv GODKJENN", key="strategy_lab_approve_confirm_v19100")
            if st.button("Godkjenn kun for manuell promoteringsvurdering", key="strategy_lab_approve_v19100"):
                try:
                    lab.approve(selected["experiment_id"], actor=actor, reason=reason, confirmation=confirmation)
                    st.success("Resultatet er godkjent for manuell vurdering. Strategien er ikke promotert.")
                    st.rerun()
                except StrategyLabError as exc:
                    st.error(str(exc))

    if approvals:
        st.markdown("#### Godkjennings- og rollbackhistorikk")
        st.dataframe(pd.DataFrame(approvals), use_container_width=True, hide_index=True)
        active = [row for row in approvals if str(row.get("status") or "").startswith("APPROVED")]
        if active:
            labels = {f"{row.get('approval_id')} | {row.get('experiment_id')}": row for row in active}
            selected_approval_label = st.selectbox("Godkjenning", list(labels), key="strategy_lab_rollback_select_v19100")
            rollback_reason = st.text_input("Rollback-begrunnelse", key="strategy_lab_rollback_reason_v19100")
            rollback_confirmation = st.text_input("Skriv RULL TILBAKE", key="strategy_lab_rollback_confirm_v19100")
            if st.button("Trekk tilbake godkjenning", key="strategy_lab_rollback_v19100"):
                try:
                    lab.rollback_approval(
                        labels[selected_approval_label]["approval_id"],
                        actor=actor,
                        reason=rollback_reason,
                        confirmation=rollback_confirmation,
                    )
                    st.success("Godkjenningen er trukket tilbake. Produksjon var ikke endret.")
                    st.rerun()
                except StrategyLabError as exc:
                    st.error(str(exc))

    st.info(
        "Technical Quality Challenger er skrivebeskyttet. Den rene tekniske produksjonsbenchmarken er fortsatt referanse, "
        "og Strategy Lab kan ikke opprette ordre eller endre produksjonsbindinger."
    )
