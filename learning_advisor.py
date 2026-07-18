"""Learning Advisor v18.6.85.

Read-only advisory layer over Paper Trading analytics, Strategy Lab,
Backtesting and Portfolio Optimizer. It creates evidence-linked hypotheses and
an approval/test queue. It never changes live rules, signal weights, paper
positions or strategies automatically.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ai_learning_foundation import learning_report
from storage_architecture import runtime_data_path

VERSION = "v18.6.85"
ADVISOR_DIR = runtime_data_path("learning_advisor")
STATE_PATH = ADVISOR_DIR / "advisor_state.json"
EXPERIMENT_QUEUE_PATH = ADVISOR_DIR / "experiment_queue.json"

VALID_STATUSES = {"NY", "TIL_VURDERING", "GODKJENT_FOR_TEST", "AVVIST", "TESTET"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _source_payloads() -> dict[str, Any]:
    root = runtime_data_path()
    return {
        "strategy_lab": _read_json(root / "strategy_lab" / "latest_runs.json", {}),
        "backtesting": _read_json(root / "backtesting" / "latest_backtest.json", {}),
        "portfolio_optimizer": _read_json(root / "portfolio_optimizer" / "latest_report.json", {}),
    }


def _stable_id(category: str, title: str) -> str:
    digest = hashlib.sha1(f"{category}|{title}".encode("utf-8")).hexdigest()[:10].upper()
    return f"LA-{digest}"


@dataclass
class Advice:
    advice_id: str
    category: str
    title: str
    hypothesis: str
    evidence: list[str]
    proposed_test: str
    guardrails: list[str]
    sample_size: int = 0
    confidence: str = "LAV"
    priority: str = "NORMAL"
    status: str = "NY"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    note: str = ""
    source_snapshot: dict[str, Any] = field(default_factory=dict)


def _confidence(sample_size: int, effect: float) -> str:
    if sample_size >= 40 and abs(effect) >= 5:
        return "HØY"
    if sample_size >= 15 and abs(effect) >= 2:
        return "MODERAT"
    return "LAV"


def _advice(category: str, title: str, hypothesis: str, evidence: Iterable[str], proposed_test: str,
            sample_size: int = 0, effect: float = 0.0, priority: str = "NORMAL",
            source_snapshot: Mapping[str, Any] | None = None) -> Advice:
    return Advice(
        advice_id=_stable_id(category, title), category=category, title=title,
        hypothesis=hypothesis, evidence=list(evidence), proposed_test=proposed_test,
        guardrails=[
            "Test kun i Strategy Lab eller Backtesting Engine.",
            "Ingen automatisk endring av live-regler eller Paper Trading.",
            "Krev ny validering på separat periode før eventuell manuell produksjonsendring.",
        ],
        sample_size=int(sample_size), confidence=_confidence(sample_size, effect),
        priority=priority, source_snapshot=dict(source_snapshot or {}),
    )


def generate_advice(report: Mapping[str, Any] | None = None,
                    sources: Mapping[str, Any] | None = None,
                    min_observations: int = 5) -> list[Advice]:
    report = dict(report or learning_report())
    sources = dict(sources or _source_payloads())
    items: list[Advice] = []

    metrics = report.get("metrics") or {}
    trade_count = int(_f(metrics.get("trade_count")))
    if trade_count < max(10, min_observations * 2):
        items.append(_advice(
            "Datakvalitet", "Bygg større beslutningsgrunnlag",
            "Datagrunnlaget er for lite til at regelendringer kan vurderes robust.",
            [f"Kun {trade_count} avsluttede handler er tilgjengelige."],
            "Fortsett datainnsamling og kjør samme strategi på flere perioder/symboler før nye terskler testes.",
            trade_count, 0.0, "HØY",
        ))

    signals = [r for r in report.get("signal_scorecard", []) if int(_f(r.get("observations"))) >= min_observations]
    if signals:
        best = max(signals, key=lambda r: (_f(r.get("avg_return_pct")), _f(r.get("hit_rate_pct"))))
        worst = min(signals, key=lambda r: (_f(r.get("avg_return_pct")), _f(r.get("hit_rate_pct"))))
        spread = _f(best.get("avg_return_pct")) - _f(worst.get("avg_return_pct"))
        items.append(_advice(
            "Signaler", f"Test høyere vekt på {best.get('name')}",
            f"{best.get('name')} kan være et mer informativt filter enn svakere signaler, men bør valideres utenfor samme datasett.",
            [f"{best.get('observations')} observasjoner", f"Treff {_f(best.get('hit_rate_pct')):.1f}%", f"Snittavkastning {_f(best.get('avg_return_pct')):.2f}%", f"Spredning mot svakeste signal {spread:.2f} prosentpoeng"],
            f"Lag en Strategy Lab-variant der {best.get('name')} brukes som ekstra entry-filter. Sammenlign mot kontrollstrategien med identiske kostnader og periode.",
            int(_f(best.get("observations"))), spread, "HØY" if spread >= 5 else "NORMAL", best,
        ))
        if _f(worst.get("avg_return_pct")) < 0:
            items.append(_advice(
                "Signaler", f"Test ekskludering av {worst.get('name')}",
                f"Handler assosiert med {worst.get('name')} har negativ gjennomsnittsavkastning i nåværende utvalg.",
                [f"{worst.get('observations')} observasjoner", f"Treff {_f(worst.get('hit_rate_pct')):.1f}%", f"Snittavkastning {_f(worst.get('avg_return_pct')):.2f}%"],
                f"Kjør A/B-backtest med og uten {worst.get('name')}. Ikke fjern signalet før out-of-sample-resultatet bekrefter effekten.",
                int(_f(worst.get("observations"))), _f(worst.get("avg_return_pct")), "HØY", worst,
            ))

    combos = [r for r in report.get("combination_analysis", []) if int(_f(r.get("observations"))) >= min_observations]
    if combos:
        best = max(combos, key=lambda r: (_f(r.get("avg_return_pct")), _f(r.get("hit_rate_pct"))))
        items.append(_advice(
            "Signalkombinasjon", f"Valider kombinasjonen {best.get('name')}",
            "Kombinasjonen kan gi bedre seleksjon enn enkeltstående signaler.",
            [f"{best.get('observations')} observasjoner", f"Treff {_f(best.get('hit_rate_pct')):.1f}%", f"Snittavkastning {_f(best.get('avg_return_pct')):.2f}%"],
            "Opprett en isolert kombinasjonsstrategi og test på minst to ikke-overlappende perioder samt mot benchmark.",
            int(_f(best.get("observations"))), _f(best.get("avg_return_pct")), "NORMAL", best,
        ))

    exits = [r for r in report.get("exit_analytics", []) if int(_f(r.get("observations"))) >= min_observations]
    if len(exits) >= 2:
        best = max(exits, key=lambda r: _f(r.get("avg_return_pct")))
        worst = min(exits, key=lambda r: _f(r.get("avg_return_pct")))
        spread = _f(best.get("avg_return_pct")) - _f(worst.get("avg_return_pct"))
        items.append(_advice(
            "Exit", f"Sammenlign {best.get('name')} mot {worst.get('name')}",
            "Exit-reglene gir ulik realisert avkastning og kan optimaliseres gjennom kontrollert testing.",
            [f"Beste: {best.get('name')} {_f(best.get('avg_return_pct')):.2f}%", f"Svakeste: {worst.get('name')} {_f(worst.get('avg_return_pct')):.2f}%", f"Forskjell {spread:.2f} prosentpoeng"],
            "Kjør identiske entries med alternative exit-profiler i Backtesting Engine. Sammenlign også drawdown, kostnader og holdingtid.",
            min(int(_f(best.get("observations"))), int(_f(worst.get("observations")))), spread, "HØY" if spread >= 5 else "NORMAL",
            {"best": best, "worst": worst},
        ))

    sectors = [r for r in report.get("sector_analysis", []) if int(_f(r.get("observations"))) >= min_observations]
    if sectors:
        best = max(sectors, key=lambda r: _f(r.get("avg_return_pct")))
        if _f(best.get("avg_return_pct")) > 0:
            items.append(_advice(
                "Marked/segment", f"Test sektortilpasning for {best.get('name')}",
                "Strategien kan ha en regimespesifikk fordel i denne sektoren.",
                [f"{best.get('observations')} observasjoner", f"Treff {_f(best.get('hit_rate_pct')):.1f}%", f"Snittavkastning {_f(best.get('avg_return_pct')):.2f}%"],
                "Kjør sektoren separat og sammenlign mot øvrige sektorer og sektorbenchmark. Bruk eksponeringsgrense i Portfolio Optimizer.",
                int(_f(best.get("observations"))), _f(best.get("avg_return_pct")), "NORMAL", best,
            ))

    confidence_rows = [r for r in report.get("confidence_calibration", []) if int(_f(r.get("observations"))) >= min_observations]
    if len(confidence_rows) >= 2:
        ordered = sorted(confidence_rows, key=lambda r: str(r.get("name")))
        rates = [_f(r.get("hit_rate_pct")) for r in ordered]
        inversions = sum(1 for a, b in zip(rates, rates[1:]) if b + 2 < a)
        if inversions:
            items.append(_advice(
                "Kalibrering", "Rekalibrer confidence-bånd i testmiljø",
                "Høyere confidence gir ikke konsekvent høyere realisert treffprosent i tilgjengelige data.",
                [f"{inversions} fall i treffprosent mellom stigende confidence-bånd.", "Bånd: " + ", ".join(f"{r.get('name')}={_f(r.get('hit_rate_pct')):.1f}%" for r in ordered)],
                "Test isotonic/båndbasert kalibrering på historiske resultater. Evaluer Brier score og out-of-sample-treff før visningsscore endres.",
                sum(int(_f(r.get("observations"))) for r in ordered), max(rates) - min(rates), "HØY", {"bands": ordered},
            ))

    backtest = sources.get("backtesting") or {}
    bt_metrics = backtest.get("metrics") or {}
    if bt_metrics:
        ret = _f(bt_metrics.get("total_return_pct"))
        bench = _f(bt_metrics.get("benchmark_return_pct"))
        dd = abs(_f(bt_metrics.get("max_drawdown_pct")))
        if ret < bench:
            items.append(_advice(
                "Backtesting", "Forbedre robusthet mot benchmark",
                "Siste backtest leverte lavere avkastning enn kjøp-og-hold-benchmark.",
                [f"Strategi {ret:.2f}%", f"Benchmark {bench:.2f}%", f"Max drawdown {dd:.2f}%"],
                "Test én endring om gangen og behold benchmark, kostnader og datasett uendret. Prioriter forbedret risikojustert avkastning fremfor kun totalavkastning.",
                int(_f(bt_metrics.get("trade_count"))), ret - bench, "HØY", bt_metrics,
            ))

    optimizer = sources.get("portfolio_optimizer") or {}
    violations = optimizer.get("violations") or optimizer.get("warnings") or []
    if violations:
        items.append(_advice(
            "Porteføljerisiko", "Test strategi under gjeldende porteføljegrenser",
            "Nye strategiforslag bør ikke vurderes isolert fra eksisterende eksponerings- og diversifiseringsbrudd.",
            [str(x.get("message") if isinstance(x, Mapping) else x) for x in list(violations)[:5]],
            "Kjør kandidaten gjennom Portfolio Optimizer med samme sektor-, posisjons- og kontantgrenser før manuell godkjenning.",
            len(violations), 0.0, "HØY", {"violations": list(violations)[:10]},
        ))

    # Deduplicate by stable ID.
    return list({item.advice_id: item for item in items}.values())


def load_state() -> dict[str, Any]:
    raw = _read_json(STATE_PATH, {"version": VERSION, "items": {}, "updated_at": ""})
    if not isinstance(raw, dict):
        return {"version": VERSION, "items": {}, "updated_at": ""}
    raw.setdefault("items", {})
    return raw


def merge_with_state(items: Sequence[Advice], state: Mapping[str, Any] | None = None) -> list[Advice]:
    state = dict(state or load_state())
    saved = state.get("items") or {}
    merged: list[Advice] = []
    for item in items:
        previous = saved.get(item.advice_id) or {}
        if previous:
            status = str(previous.get("status") or item.status)
            item.status = status if status in VALID_STATUSES else "NY"
            item.note = str(previous.get("note") or "")
            item.created_at = str(previous.get("created_at") or item.created_at)
            item.updated_at = str(previous.get("updated_at") or item.updated_at)
        merged.append(item)
    return merged


def save_item(item: Advice) -> None:
    state = load_state()
    item.updated_at = _now_iso()
    state["version"] = VERSION
    state["updated_at"] = item.updated_at
    state.setdefault("items", {})[item.advice_id] = asdict(item)
    _write_json(STATE_PATH, state)


def queue_experiment(item: Advice) -> None:
    queue = _read_json(EXPERIMENT_QUEUE_PATH, {"version": VERSION, "experiments": []})
    rows = list(queue.get("experiments") or [])
    payload = asdict(item) | {"queued_at": _now_iso(), "target": "Strategy Lab / Backtesting Engine", "execution": "MANUAL_ONLY"}
    rows = [r for r in rows if r.get("advice_id") != item.advice_id]
    rows.append(payload)
    queue.update({"version": VERSION, "updated_at": _now_iso(), "experiments": rows})
    _write_json(EXPERIMENT_QUEUE_PATH, queue)


def advisor_report(min_observations: int = 5) -> dict[str, Any]:
    report = learning_report()
    sources = _source_payloads()
    items = merge_with_state(generate_advice(report, sources, min_observations))
    return {
        "version": VERSION,
        "generated_at": _now_iso(),
        "learning_loop": "OFF",
        "automatic_changes": "OFF",
        "approval_required": True,
        "source_trade_count": int(_f((report.get("metrics") or {}).get("trade_count"))),
        "items": [asdict(x) for x in items],
    }


def render_learning_advisor() -> None:
    import streamlit as st
    try:
        import pandas as pd
    except Exception:
        pd = None

    st.markdown("#### 🧭 Rådgivning – Learning Advisor")
    st.caption("Analyserer egne resultater og foreslår kontrollerte eksperimenter. Alle forslag krever manuell vurdering. Learning Loop og automatiske regelendringer er AV.")

    c1, c2, c3 = st.columns([1, 1, 2])
    min_obs = c1.number_input("Min. observasjoner", min_value=2, max_value=100, value=5, step=1, key="la_min_obs_v18685")
    status_filter = c2.selectbox("Status", ["Alle"] + sorted(VALID_STATUSES), key="la_status_v18685")
    c3.info("Arbeidsflyt: NY → TIL VURDERING → GODKJENT FOR TEST → TESTET. Godkjenning legger kun hypotesen i en eksperimentkø.")

    report = advisor_report(int(min_obs))
    items = [Advice(**row) for row in report["items"]]
    if status_filter != "Alle":
        items = [x for x in items if x.status == status_filter]

    all_items = [Advice(**row) for row in advisor_report(int(min_obs))["items"]]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Forslag", len(all_items))
    k2.metric("Høy prioritet", sum(x.priority == "HØY" for x in all_items))
    k3.metric("Godkjent for test", sum(x.status == "GODKJENT_FOR_TEST" for x in all_items))
    k4.metric("Learning Loop", "OFF")

    tabs = st.tabs(["Forslag", "Eksperimentkø", "Metode og guardrails", "Eksport"])
    with tabs[0]:
        if not items:
            st.info("Ingen forslag matcher filteret. Senk minimum antall observasjoner eller samle flere avsluttede handler.")
        for item in items:
            badge = f"{item.priority} · {item.confidence} evidens · n={item.sample_size} · {item.status}"
            with st.expander(f"{item.category}: {item.title} — {badge}", expanded=item.priority == "HØY"):
                st.markdown(f"**Hypotese:** {item.hypothesis}")
                st.markdown("**Evidens:**")
                for evidence in item.evidence:
                    st.write(f"• {evidence}")
                st.markdown(f"**Foreslått test:** {item.proposed_test}")
                st.markdown("**Sikkerhetskrav:** " + " ".join(item.guardrails))
                note = st.text_area("Notat", value=item.note, key=f"la_note_{item.advice_id}")
                a, b, c, d = st.columns(4)
                if a.button("Til vurdering", key=f"la_review_{item.advice_id}"):
                    item.status, item.note = "TIL_VURDERING", note
                    save_item(item); st.rerun()
                if b.button("Godkjenn for test", key=f"la_approve_{item.advice_id}"):
                    item.status, item.note = "GODKJENT_FOR_TEST", note
                    save_item(item); queue_experiment(item); st.rerun()
                if c.button("Avvis", key=f"la_reject_{item.advice_id}"):
                    item.status, item.note = "AVVIST", note
                    save_item(item); st.rerun()
                if d.button("Marker testet", key=f"la_tested_{item.advice_id}"):
                    item.status, item.note = "TESTET", note
                    save_item(item); st.rerun()
                with st.expander("Kildesnapshot", expanded=False):
                    st.json(item.source_snapshot)

    with tabs[1]:
        queue = _read_json(EXPERIMENT_QUEUE_PATH, {"experiments": []})
        rows = queue.get("experiments") or []
        st.caption("Køen er en arbeidsliste. Den starter ingen backtest og endrer ingen strategi automatisk.")
        if rows:
            display = [{"ID": r.get("advice_id"), "Kategori": r.get("category"), "Test": r.get("proposed_test"), "Kølagt": r.get("queued_at"), "Utførelse": r.get("execution")} for r in rows]
            st.dataframe(pd.DataFrame(display) if pd is not None else display, use_container_width=True, hide_index=True)
        else:
            st.info("Ingen hypoteser er godkjent for test ennå.")

    with tabs[2]:
        st.markdown("""
**Advisor-prinsipper**

1. Forslag bygger på dokumenterte Paper Trading-resultater og tilgjengelige lab-/backtestrapporter.
2. Små utvalg merkes med lav evidens og skal ikke brukes til produksjonsendringer.
3. Ett parameter eller én hypotese testes om gangen mot en uendret kontroll.
4. Out-of-sample-validering og handelskostnader må inkluderes.
5. Ingen forslag aktiveres automatisk; brukerens eksplisitte godkjenning er påkrevd.
""")
        st.warning("Learning Advisor er beslutningsstøtte, ikke investeringsråd. Historiske resultater garanterer ikke fremtidige resultater.")

    with tabs[3]:
        payload = json.dumps(report, ensure_ascii=False, indent=2)
        st.download_button("Last ned Advisor-rapport (JSON)", payload, "LEARNING_ADVISOR_v18_6_85.json", "application/json")
        if pd is not None:
            csv = pd.DataFrame(report["items"]).to_csv(index=False).encode("utf-8-sig")
            st.download_button("Last ned forslag (CSV)", csv, "LEARNING_ADVISOR_v18_6_85.csv", "text/csv")
        st.caption(f"Runtime-state: {STATE_PATH} · Eksperimentkø: {EXPERIMENT_QUEUE_PATH}")
