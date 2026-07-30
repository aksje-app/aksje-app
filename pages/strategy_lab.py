"""Strategy Lab, controlled promotion and rollback workspace for v19.12.0."""
from __future__ import annotations

from typing import Any
import pandas as pd

from services.strategy_lab_service import StrategyLabError
from services.strategy_promotion_service import StrategyPromotionError


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
    promotion_service = app_context.services.strategy_promotions
    promotions = promotion_service.recent_promotions()

    st.markdown("### \U0001f9ea Strategy Lab")
    st.caption(
        "Sammenlign produksjonsbenchmark og skrivebeskyttede challengere p\u00e5 de samme snapshotene. "
        "Lab-kj\u00f8ringer kan ikke handle, endre produksjonsbinding eller promotere en strategi automatisk."
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Eksperimenter", len(experiments))
    c2.metric("Lab-kj\u00f8ringer", len(runs))
    c3.metric("Godkjenninger", sum(1 for row in approvals if str(row.get("status") or "").startswith("APPROVED")))
    c4.metric("Produksjonsbinding", (registry.production_for_family("technical") or {}).get("version_id") or "Ukjent")

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
        st.dataframe(pd.DataFrame(display), width="stretch", hide_index=True)

        labels = {f"{row.get('name')} | {row.get('status')} | {row.get('experiment_id')}": row for row in experiments}
        selected_label = st.selectbox("Velg eksperiment", list(labels), key="strategy_lab_selected_v19100")
        selected = labels[selected_label]
        r1, r2, r3 = st.columns([1, 1, 1])
        snapshot_count = r1.number_input("Bruk siste antall snapshots", min_value=1, max_value=500, value=30, step=1)
        settle_outcomes = r2.checkbox(
            "Oppdater observerte utfall",
            value=True,
            key="strategy_lab_settle_outcomes_v19110",
            help="Henter etterf\u00f8lgende sluttkurser og lagrer 1-, 5- og 20-handelsdagers utfall separat. Snapshotene endres ikke.",
        )
        if r3.button("Kj\u00f8r skrivebeskyttet replay", key="strategy_lab_run_v19110"):
            try:
                snapshots = sorted(app_context.services.repositories.market_snapshots.list(), key=lambda row: str(row.get("captured_at") or ""))
                snapshot_ids = [row.get("snapshot_id") for row in snapshots[-int(snapshot_count):] if row.get("snapshot_id")]
                result = lab.run_experiment(selected["experiment_id"], snapshot_ids=snapshot_ids, actor=actor, settle_outcomes=settle_outcomes)
                st.success(f"Lab-kj\u00f8ring fullf\u00f8rt: {result.get('decision_count')} beslutninger, {result.get('error_count')} feil.")
                st.rerun()
            except StrategyLabError as exc:
                st.error(str(exc))

        latest_run_id = selected.get("latest_lab_run_id")
        latest_run = next((row for row in runs if row.get("lab_run_id") == latest_run_id), None)
        if latest_run:
            st.markdown("#### Strategisammenligning")
            metrics = list(latest_run.get("metrics") or [])
            if metrics:
                st.dataframe(pd.DataFrame(metrics), width="stretch", hide_index=True)

            diagnostics = dict(latest_run.get("quality_diagnostics") or {})
            if diagnostics:
                st.markdown("#### Datadekning og blokkårsaker")
                q1, q2, q3, q4 = st.columns(4)
                q1.metric("Kvalitetsvurderinger", diagnostics.get("quality_decisions", 0))
                q2.metric("Tilstrekkelig evidens", diagnostics.get("sufficient_evidence_count", 0))
                q3.metric("Mangler evidens", diagnostics.get("insufficient_evidence_count", 0))
                q4.metric("Evidensdekning", f"{diagnostics.get('sufficient_evidence_pct', 0):.1f} %")
                component_rows = list(diagnostics.get("components") or [])
                if component_rows:
                    st.caption("MANGLER DATA og UGYLDIG DATA er separate fra UNDER TERSKEL. Manglende data regnes ikke som svak verdi.")
                    st.dataframe(pd.DataFrame(component_rows), width="stretch", hide_index=True)
                blocker_rows = list(diagnostics.get("blocker_counts") or [])
                combo_rows = list(diagnostics.get("blocker_combinations") or [])
                b1, b2 = st.columns(2)
                with b1:
                    st.markdown("**Blokkårsaker**")
                    if blocker_rows:
                        st.dataframe(pd.DataFrame(blocker_rows), width="stretch", hide_index=True)
                    else:
                        st.info("Ingen terskelblokkeringer i denne kjøringen.")
                with b2:
                    st.markdown("**Samtidige blokkårsaker**")
                    if combo_rows:
                        st.dataframe(pd.DataFrame(combo_rows), width="stretch", hide_index=True)
                    else:
                        st.info("Ingen kombinerte blokkeringer.")

            outcome_coverage = dict(latest_run.get("outcome_coverage") or {})
            outcome_settlement = dict(latest_run.get("outcome_settlement") or {})
            if outcome_coverage:
                st.markdown("#### Observerte utfall")
                o1, o2, o3, o4 = st.columns(4)
                o1.metric("Kandidater", outcome_coverage.get("selected_candidates", 0))
                o2.metric("5-dagersutfall", outcome_coverage.get("observed_candidates", 0))
                o3.metric("Mangler utfall", outcome_coverage.get("missing_outcomes", 0))
                o4.metric("Utfallsdekning", f"{outcome_coverage.get('coverage_pct', 0):.1f} %")
                if outcome_settlement.get("requested"):
                    st.caption(
                        f"Nyregistrert: {outcome_settlement.get('created', 0)} | "
                        f"Allerede lagret: {outcome_settlement.get('existing', 0)} | "
                        f"Ikke modent enn\u00e5: {outcome_settlement.get('unavailable', 0)} | "
                        f"Feil: {outcome_settlement.get('error_count', 0)}. "
                        "Utfall lagres separat og brukes aldri i den opprinnelige beslutningen."
                    )

            attribution = list(latest_run.get("result_attribution") or [])
            if attribution:
                st.markdown("#### Resultatattribusjon")
                flat = [{k: v for k, v in row.items() if k not in {"blocker_outcomes", "component_attribution"}} for row in attribution]
                st.dataframe(pd.DataFrame(flat), width="stretch", hide_index=True)
                if not any(bool(row.get("attribution_reliable")) for row in attribution):
                    st.warning("Resultatattribusjonen har foreløpig færre enn 20 observerte utfall per sammenligning. Den er informativ, men ikke sterk nok for promotering.")
                for row in attribution:
                    label = str(row.get("challenger_version_id") or "Challenger")
                    with st.expander(f"Attribusjonsdetaljer – {label}", expanded=False):
                        blocker_outcomes = list(row.get("blocker_outcomes") or [])
                        component_attribution = list(row.get("component_attribution") or [])
                        if blocker_outcomes:
                            st.markdown("**Utfall for filtrerte kjøp per blokkårsak**")
                            st.dataframe(pd.DataFrame(blocker_outcomes), width="stretch", hide_index=True)
                        if component_attribution:
                            st.markdown("**Gjennomsnittlig scorebidrag per komponent**")
                            st.dataframe(pd.DataFrame(component_attribution), width="stretch", hide_index=True)
                        if not blocker_outcomes and not component_attribution:
                            st.info("Ingen attribusjonsdetaljer tilgjengelig ennå.")

            split = dict(latest_run.get("split") or {})
            st.caption(
                f"Tidsordnet split: {split.get('train_snapshots', 0)} trening / "
                f"{split.get('validation_snapshots', 0)} validering. Ingen fremtidsdata brukes i beslutningen; utfall kobles kun på etterpå for attribusjon. "
                "Utførelse og produksjonspåvirkning er deaktivert."
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
        st.dataframe(pd.DataFrame(approvals), width="stretch", hide_index=True)
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

    st.markdown("#### Produksjonsgodkjenning og promotering")
    active_approvals = [row for row in approvals if str(row.get("status") or "") == "APPROVED_FOR_MANUAL_PROMOTION_REVIEW"]
    if not active_approvals:
        st.info("Ingen aktive godkjenninger er klare for promoteringsvurdering.")
    else:
        approval_labels = {f"{row.get('approval_id')} | {row.get('experiment_id')}": row for row in active_approvals}
        chosen_approval_label = st.selectbox("Godkjenning for pre-flight", list(approval_labels), key="strategy_promotion_approval_v19120")
        chosen_approval = approval_labels[chosen_approval_label]
        experiment = next((row for row in experiments if row.get("experiment_id") == chosen_approval.get("experiment_id")), {})
        targets = [str(item) for item in experiment.get("challenger_version_ids") or []]
        if targets:
            chosen_target = st.selectbox("Challenger som skal vurderes", targets, key="strategy_promotion_target_v19120")
            preflight = promotion_service.preflight(str(chosen_approval.get("approval_id") or ""), chosen_target)
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Pre-flight", "BESTÅTT" if preflight.get("eligible") else "STOPPET")
            p2.metric("Observerte utfall", preflight.get("outcome_pairs", 0))
            p3.metric("Utfallsdekning", f"{float(preflight.get('outcome_coverage_pct') or 0):.1f} %")
            p4.metric("Evidensdekning", f"{float(preflight.get('sufficient_evidence_pct') or 0):.1f} %")
            if preflight.get("blockers"):
                st.error("Pre-flight stopper promotering: " + " | ".join(preflight.get("blockers") or []))
            if preflight.get("warnings"):
                st.warning(" | ".join(preflight.get("warnings") or []))
            promote_reason = st.text_area("Promoteringsbegrunnelse", key="strategy_promotion_reason_v19120")
            promote_confirmation = st.text_input("Skriv PROMOTER", key="strategy_promotion_confirm_v19120")
            if st.button("Aktiver challenger i Paper Trading", disabled=not bool(preflight.get("eligible")), key="strategy_promote_v19120"):
                try:
                    promotion_service.promote(
                        str(chosen_approval.get("approval_id") or ""), chosen_target, actor=actor,
                        reason=promote_reason, confirmation=promote_confirmation,
                    )
                    st.success("Strategien er aktivert som ny Paper Trading-produksjonsstrategi. Forrige binding er lagret for rollback.")
                    st.rerun()
                except StrategyPromotionError as exc:
                    st.error(str(exc))

    st.markdown("#### Promoterings- og rollbackhistorikk")
    if promotions:
        st.dataframe(pd.DataFrame(promotions), width="stretch", hide_index=True)
        active_promotions = [row for row in promotions if str(row.get("status") or "") == "ACTIVE"]
        if active_promotions:
            promotion_labels = {f"{row.get('target_version_id')} | {row.get('promotion_id')}": row for row in active_promotions}
            chosen_promotion_label = st.selectbox("Aktiv promotering", list(promotion_labels), key="strategy_active_promotion_v19120")
            rollback_reason = st.text_area("Rollback-begrunnelse", key="strategy_production_rollback_reason_v19120")
            rollback_confirmation = st.text_input("Skriv RULL TILBAKE", key="strategy_production_rollback_confirm_v19120")
            if st.button("Gjenopprett forrige produksjonsstrategi", key="strategy_production_rollback_v19120"):
                try:
                    promotion_service.rollback(
                        str(promotion_labels[chosen_promotion_label].get("promotion_id") or ""),
                        actor=actor, reason=rollback_reason, confirmation=rollback_confirmation,
                    )
                    st.success("Forrige produksjonsstrategi er gjenopprettet og rollback er auditert.")
                    st.rerun()
                except StrategyPromotionError as exc:
                    st.error(str(exc))
    else:
        st.info("Ingen strategipromoteringer er gjennomført.")

    st.info(
        "Automatisk promotering er av. En promotering endrer bare den kanoniske Paper Trading-bindingen; "
        "Autonomis eksplisitte tekniske versjonsbinding og alle megler-/livegrenser forblir urørt."
    )
