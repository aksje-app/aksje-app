from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core_models import ServiceResult
from services.state_service import get_state_service
from services.storage_service import get_storage_service


ANALYSIS_PIPELINE_VERSION = "v18.6.3bv"
PIPELINE_INPUTS_STATE_KEY = "analysis_pipeline_inputs_v1863bv"
PIPELINE_OUTPUTS_STATE_KEY = "analysis_pipeline_outputs_v1863bv"
PIPELINE_LATEST_INPUT_KEY = "analysis_pipeline_latest_input_v1863bv"
PIPELINE_LATEST_OUTPUT_KEY = "analysis_pipeline_latest_output_v1863bv"
PIPELINE_PENDING_NAV_KEY = "analysis_pipeline_pending_nav_v1863bw"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _norm_ticker(value: Any) -> str:
    return _clean(value).upper().replace(" ", "")


INVALID_PIPELINE_TICKERS = {
    "RAW", "RAW_DATA", "SCORE", "SCORES", "SCORE_PARTS", "SHARED_SCORE",
    "SMART_SCORE", "AI_SCORE", "STRENGTH", "MOMENTUM_STRENGTH", "RISK",
    "RISK_SCORE", "QUALITY_SCORE", "DATA_QUALITY", "STATUS", "SOURCE",
    "REASON", "NOTE", "NOTES", "INPUT", "OUTPUT", "CANDIDATE", "CANDIDATES",
    "CONTEXT", "METADATA", "CONFIG", "REQUEST", "SUMMARY", "ERRORS",
    "EVIDENCE", "EVIDENCE_ITEMS", "POSITIONS", "HOLDINGS", "TRADES",
}
INVALID_PIPELINE_TICKER_FRAGMENTS = ("SCORE_PART", "MANGLER", "MISSING", "RAW_")


def _is_valid_pipeline_ticker(value: Any) -> bool:
    ticker = _norm_ticker(value)
    if not ticker or ticker in INVALID_PIPELINE_TICKERS:
        return False
    if any(fragment in ticker for fragment in INVALID_PIPELINE_TICKER_FRAGMENTS):
        return False
    if len(ticker) > 18:
        return False
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,17}", ticker):
        return False
    if not any(ch.isalpha() for ch in ticker):
        return False
    if "." not in ticker and "-" not in ticker and len(ticker) > 6:
        return False
    return True


def _first(row: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
        low = str(key).lower()
        if low in lowered and lowered[low] not in (None, ""):
            return lowered[low]
    return default


def _float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _score(value: Any, default: float = 0.0) -> float:
    number = _float(value, None)
    if number is None:
        return float(default)
    if 0.0 <= number <= 1.0:
        number *= 100.0
    elif 0.0 <= number <= 10.0:
        number *= 10.0
    return max(0.0, min(100.0, float(number)))


@dataclass(frozen=True)
class PipelineStage:
    stage_id: str
    label: str
    purpose: str
    next_stage_id: str = ""
    previous_stage_id: str = ""
    report_focus: Sequence[str] = field(default_factory=tuple)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


STAGE_ORDER: tuple[PipelineStage, ...] = (
    PipelineStage(
        "data_foundation",
        "Dataunderlag",
        "Kontroller datakilder og gjoer underlaget klart for Test 2. Ingen analyse kjoeres her.",
        next_stage_id="market_ranking",
        report_focus=("dataunderlag", "oppdatert dato", "dekning", "mangler"),
    ),
    PipelineStage(
        "market_ranking",
        "Marked/rangering",
        "Bred markedsskanning som finner brutto-kandidater.",
        previous_stage_id="data_foundation",
        next_stage_id="smart_ai",
        report_focus=("univers", "score", "marked", "datakvalitet"),
    ),
    PipelineStage(
        "smart_ai",
        "Smart AI-filter",
        "Streng filtrering etter risiko, sektor, momentum, kvalitet og score.",
        previous_stage_id="market_ranking",
        next_stage_id="top_picks",
        report_focus=("filtre", "forkastede kandidater", "smart_score", "risiko"),
    ),
    PipelineStage(
        "top_picks",
        "Top Picks",
        "Shortlist over eksisterende ranking uten nye tunge kall.",
        previous_stage_id="smart_ai",
        next_stage_id="early_warning",
        report_focus=("kortliste", "terskel", "timing", "sendt videre"),
    ),
    PipelineStage(
        "early_warning",
        "Early Warning",
        "Ferske signaler: insider/bjellesau, nyheter, katalysatorer og forventningsendring.",
        previous_stage_id="top_picks",
        next_stage_id="alpha_radar",
        report_focus=("ferske funn", "kilder", "insider/bjellesau", "nyheter"),
    ),
    PipelineStage(
        "alpha_radar",
        "Alpha Radar",
        "Dypere helhetsvurdering av kandidatene.",
        previous_stage_id="early_warning",
        next_stage_id="auto_test_lab",
        report_focus=("hypotese", "evidens", "risiko", "bekreftelse"),
    ),
    PipelineStage(
        "auto_test_lab",
        "Auto Test Lab",
        "Validerer kandidater, kombinasjoner, datakvalitet og forkastelsesgrunner.",
        previous_stage_id="alpha_radar",
        next_stage_id="decision_support",
        report_focus=("decision_quality", "tester", "forkastet", "kombinasjoner"),
    ),
    PipelineStage(
        "decision_support",
        "Beslutningsgrunnlag",
        "Samler funn til kjop, vent eller unnga.",
        previous_stage_id="auto_test_lab",
        next_stage_id="portfolio_analysis",
        report_focus=("beslutning", "confidence", "mangler", "trigger"),
    ),
    PipelineStage(
        "portfolio_analysis",
        "Portefoljeanalyse",
        "Sjekker vekting, risiko, sektor, valuta og total portefolje.",
        previous_stage_id="decision_support",
        next_stage_id="paper_trading",
        report_focus=("vekting", "risiko", "sektor", "valuta"),
    ),
    PipelineStage(
        "paper_trading",
        "Paper Trading",
        "Trygg testportefolje for forste praktiske utvalg.",
        previous_stage_id="portfolio_analysis",
        report_focus=("ordregrunnlag", "posisjoner", "oppfolging", "laering"),
    ),
)

STAGES_BY_ID = {stage.stage_id: stage for stage in STAGE_ORDER}

STAGE_PANEL_LABELS: Dict[str, str] = {
    "data_foundation": "1. Dataunderlag",
    "market_ranking": "🏆 Marked/rangering",
    "smart_ai": "Analyseunivers",
    "top_picks": "⭐ Top Picks",
    "early_warning": "Alpha Radar",
    "alpha_radar": "Alpha Radar",
    "auto_test_lab": "🔬 Auto Test Lab",
    "decision_support": "Beslutningsgrunnlag",
    "portfolio_analysis": "📊 Porteføljeanalyse",
    "paper_trading": "🧪 Paper Trading",
}

STAGE_GROUPS: Dict[str, str] = {
    "data_foundation": "Marked og signaler",
    "market_ranking": "Marked og signaler",
    "smart_ai": "Analyse og prognose",
    "top_picks": "Marked og signaler",
    "early_warning": "Marked og signaler",
    "alpha_radar": "Marked og signaler",
    "auto_test_lab": "Testing og portefolje",
    "decision_support": "Marked og signaler",
    "portfolio_analysis": "Testing og portefolje",
    "paper_trading": "Testing og portefolje",
}

STAGE_DEFAULT_WIDGETS: Dict[str, Dict[str, Any]] = {
    "market_ranking": {
        "cc_ranking_market_v18535": "Dataunderlag",
        "cc_ranking_limit_v18535": 30,
    },
    "smart_ai": {
        "ai_universe_mode_draft_v1853": "Analyseflyt input",
        "ai_universe_scopes_draft_v1853": ["Analyseflyt input"],
    },
    "top_picks": {
        "cc_top_picks_scope_v1863s": "Analyseflyt input",
        "cc_top_picks_limit_v1863s": 30,
    },
    "early_warning": {
        "alpha_radar_engine_v1863au": "Early Warning V1",
        "alpha_radar_scope_v1863au": "Analyseflyt input",
        "alpha_radar_mode_v1863au": "Insider og bjellesauer",
        "alpha_radar_precision_v1863au": "Balansert",
    },
    "alpha_radar": {
        "alpha_radar_engine_v1863au": "Alpha Radar",
        "alpha_radar_scope_v1863au": "Analyseflyt input",
        "alpha_radar_mode_v1863au": "Insider og bjellesauer",
        "alpha_radar_precision_v1863au": "Balansert",
    },
    "auto_test_lab": {
        "auto_lab_mode_v18543": "Aksjer",
        "auto_lab_scope_v18537": "Analyseflyt input",
        "auto_lab_target_v18537": "Balansert",
        "auto_lab_test_mode_v18537": "Normal",
        "auto_lab_limit_v18537": 20,
    },
    "portfolio_analysis": {
        "mixed_portfolio_stock_source_v18544": "Analyseflyt input",
        "mixed_portfolio_fund_source_v18544": "Ingen",
        "mixed_portfolio_profile_v18544": "Balansert",
    },
}


def stage_definitions() -> List[Dict[str, Any]]:
    return [stage.as_dict() for stage in STAGE_ORDER]


def stage_number(stage_id: str) -> int:
    for idx, stage in enumerate(STAGE_ORDER, start=1):
        if stage.stage_id == stage_id:
            return idx
    return 0


def stage_wizard_info(stage_id: str) -> Dict[str, Any]:
    stage = STAGES_BY_ID.get(str(stage_id or ""))
    if stage is None:
        return {}
    nr = stage_number(stage.stage_id)
    next_stage = STAGES_BY_ID.get(stage.next_stage_id)
    previous_stage = STAGES_BY_ID.get(stage.previous_stage_id)
    return {
        "stage_id": stage.stage_id,
        "test_number": nr,
        "test_label": f"Test {nr}" if stage.stage_id != "data_foundation" else "Steg 1",
        "wizard_label": (
            f"Steg 1 av {len(STAGE_ORDER)}: {stage.label}"
            if stage.stage_id == "data_foundation"
            else f"Test {nr} av {len(STAGE_ORDER)}: {stage.label}"
        ),
        "label": stage.label,
        "purpose": stage.purpose,
        "panel_label": STAGE_PANEL_LABELS.get(stage.stage_id, stage.label),
        "group": STAGE_GROUPS.get(stage.stage_id, ""),
        "next_stage_id": stage.next_stage_id,
        "next_label": next_stage.label if next_stage else "",
        "next_test_number": stage_number(stage.next_stage_id) if stage.next_stage_id else 0,
        "previous_stage_id": stage.previous_stage_id,
        "previous_label": previous_stage.label if previous_stage else "",
        "defaults": dict(STAGE_DEFAULT_WIDGETS.get(stage.stage_id, {})),
        "auto_run": False,
    }


def next_stage_id(stage_id: str) -> str:
    stage = STAGES_BY_ID.get(stage_id)
    return stage.next_stage_id if stage is not None else ""


def previous_stage_id(stage_id: str) -> str:
    stage = STAGES_BY_ID.get(stage_id)
    return stage.previous_stage_id if stage is not None else ""


def _candidate_score(row: Mapping[str, Any]) -> float:
    for key in (
        "shared_score",
        "decision_quality",
        "decision_score",
        "early_warning_score",
        "hidden_potential_score",
        "alpha_score",
        "smart_score",
        "ai_score",
        "score",
    ):
        if row.get(key) not in (None, ""):
            return _score(row.get(key))
    return 0.0


def normalize_candidate_rows(
    rows: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None,
    *,
    source_stage_id: str = "",
    source_label: str = "",
    max_items: int | None = None,
) -> List[Dict[str, Any]]:
    if isinstance(rows, Mapping):
        source_rows = rows.get("ranked") or rows.get("shared_ranking_rows") or rows.get("candidates") or rows.get("top_picks") or []
    else:
        source_rows = list(rows or [])

    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for idx, row in enumerate(source_rows, start=1):
        if not isinstance(row, Mapping):
            continue
        raw = dict(row)
        candidate = raw.get("candidate") if isinstance(raw.get("candidate"), Mapping) else {}
        ticker = _norm_ticker(_first(raw, ("ticker", "symbol", "Ticker"), _first(candidate, ("ticker", "symbol"), "")))
        name = _clean(_first(raw, ("name", "company", "Selskap"), _first(candidate, ("name", "company"), ticker)))
        if ticker and not _is_valid_pipeline_ticker(ticker):
            continue
        if not ticker and source_stage_id != "data_foundation":
            continue
        if not ticker and not name:
            continue
        identity = f"ticker:{ticker}" if ticker else f"name:{name.lower()}"
        if identity in seen:
            continue
        seen.add(identity)
        score = _candidate_score(raw)
        source = _clean(_first(raw, ("decision_source", "source", "mode"), source_label or source_stage_id))
        normalized = {
            "ticker": ticker,
            "name": name or ticker,
            "market": _clean(_first(raw, ("market", "source_market", "Marked"), _first(candidate, ("market",), ""))),
            "source": source or source_label or source_stage_id,
            "source_stage_id": source_stage_id,
            "rank": int(_float(_first(raw, ("shared_rank", "rank"), idx), idx) or idx),
            "score": round(score, 1),
            "recommended_action": _clean(_first(raw, ("shared_recommended_action", "recommended_action", "decision", "signal"), "")),
            "reason": _clean(_first(raw, ("reason", "why", "thesis", "note"), "")),
            "evidence_items": list(raw.get("evidence_items") or []) if isinstance(raw.get("evidence_items"), list) else [],
            "raw": raw,
        }
        out.append(normalized)

    out.sort(key=lambda item: (float(item.get("score") or 0.0), -int(item.get("rank") or 999999)), reverse=True)
    limit = int(max_items or 0)
    if limit > 0:
        out = out[:limit]
    for idx, row in enumerate(out, start=1):
        row["pipeline_rank"] = idx
    return out


def standard_report_outline(stage_id: str | None = None) -> List[str]:
    base = [
        "Sammendrag",
        "Kandidatliste",
        "Score og rangering",
        "Nye funn siden forrige steg",
        "Kilder og direkte lenker der de finnes",
        "Datakvalitet og mangler",
        "Hva sendes videre",
        "Hva forkastes",
        "Modulens egne detaljer",
    ]
    stage = STAGES_BY_ID.get(str(stage_id or ""))
    if stage and stage.report_focus:
        base.insert(3, "Stegfokus: " + ", ".join(stage.report_focus))
    return base


class AnalysisPipelineService:
    def __init__(self, state_service=None, storage_service=None):
        self.state = state_service or get_state_service()
        self.storage = storage_service or get_storage_service()

    def _state_map(self, key: str) -> Dict[str, Any]:
        current = self.state.get(key, {}) or {}
        return dict(current) if isinstance(current, Mapping) else {}

    def _write_package(self, package: Mapping[str, Any]) -> None:
        stage_id = str(package.get("stage_id") or "")
        package_type = str(package.get("package_type") or "output")
        state_key = PIPELINE_INPUTS_STATE_KEY if package_type == "input" else PIPELINE_OUTPUTS_STATE_KEY
        latest_key = PIPELINE_LATEST_INPUT_KEY if package_type == "input" else PIPELINE_LATEST_OUTPUT_KEY
        bucket = self._state_map(state_key)
        bucket[stage_id] = dict(package)
        self.state.set(state_key, bucket)
        self.state.set(latest_key, dict(package))
        folder = "inputs" if package_type == "input" else "outputs"
        self.storage.write_json(f"analysis_pipeline/{folder}/{stage_id}.json", dict(package))
        self.storage.write_json(f"analysis_pipeline/latest_{package_type}.json", dict(package))
        self.storage.append_jsonl("analysis_pipeline/history.jsonl", dict(package))

    def _load_package(self, stage_id: str, package_type: str) -> Dict[str, Any]:
        state_key = PIPELINE_INPUTS_STATE_KEY if package_type == "input" else PIPELINE_OUTPUTS_STATE_KEY
        bucket = self._state_map(state_key)
        package = bucket.get(stage_id)
        if isinstance(package, Mapping):
            return dict(package)
        folder = "inputs" if package_type == "input" else "outputs"
        stored = self.storage.read_json(f"analysis_pipeline/{folder}/{stage_id}.json", default={}) or {}
        return dict(stored) if isinstance(stored, Mapping) else {}

    def make_package(
        self,
        stage_id: str,
        rows: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None,
        *,
        package_type: str = "output",
        source_label: str = "",
        origin_stage_id: str = "",
        source_package_id: str = "",
        context: Mapping[str, Any] | None = None,
        max_items: int | None = None,
    ) -> Dict[str, Any]:
        stage = STAGES_BY_ID.get(stage_id)
        if stage is None:
            raise ValueError(f"Ukjent analyseflyt-steg: {stage_id}")
        candidates = normalize_candidate_rows(
            rows,
            source_stage_id=origin_stage_id or stage_id,
            source_label=source_label or stage.label,
            max_items=max_items,
        )
        generated_at = _now_iso()
        package_id = f"{stage_id}:{package_type}:{generated_at}"
        return {
            "version": ANALYSIS_PIPELINE_VERSION,
            "package_id": package_id,
            "package_type": package_type,
            "stage_id": stage_id,
            "stage_label": stage.label,
            "origin_stage_id": origin_stage_id or (previous_stage_id(stage_id) if package_type == "input" else stage_id),
            "source_package_id": source_package_id,
            "source_label": source_label or stage.label,
            "status": "ready_for_stage" if package_type == "input" else "completed",
            "generated_at": generated_at,
            "candidate_count": len(candidates),
            "tickers": [row.get("ticker") for row in candidates if row.get("ticker")],
            "candidates": candidates,
            "next_stage_id": next_stage_id(stage_id),
            "previous_stage_id": previous_stage_id(stage_id),
            "context": dict(context or {}),
            "report_outline": standard_report_outline(stage_id),
            "auto_run": False,
        }

    def save_stage_input(
        self,
        stage_id: str,
        rows: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None,
        *,
        origin_stage_id: str = "",
        source_label: str = "",
        source_package_id: str = "",
        context: Mapping[str, Any] | None = None,
        max_items: int | None = None,
    ) -> ServiceResult:
        package = self.make_package(
            stage_id,
            rows,
            package_type="input",
            source_label=source_label,
            origin_stage_id=origin_stage_id,
            source_package_id=source_package_id,
            context=context,
            max_items=max_items,
        )
        self._write_package(package)
        return ServiceResult(ok=True, status="ok", message=f"{package['candidate_count']} kandidater klare for {package['stage_label']}.", data={"package": package})

    def save_stage_output(
        self,
        stage_id: str,
        rows: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None,
        *,
        source_label: str = "",
        context: Mapping[str, Any] | None = None,
        max_items: int | None = None,
        auto_handoff: bool = True,
    ) -> ServiceResult:
        output = self.make_package(
            stage_id,
            rows,
            package_type="output",
            source_label=source_label,
            origin_stage_id=stage_id,
            context=context,
            max_items=max_items,
        )
        self._write_package(output)
        handoff: Dict[str, Any] | None = None
        target = next_stage_id(stage_id)
        if auto_handoff and target and output.get("candidates"):
            handoff = self.make_package(
                target,
                output.get("candidates") or [],
                package_type="input",
                source_label=f"Fra {output.get('stage_label')}",
                origin_stage_id=stage_id,
                source_package_id=str(output.get("package_id") or ""),
                context={"handoff_from": stage_id, "source_context": dict(context or {})},
                max_items=max_items,
            )
            self._write_package(handoff)
        return ServiceResult(
            ok=True,
            status="ok",
            message=f"{output['candidate_count']} kandidater lagret fra {output['stage_label']}.",
            data={"output_package": output, "handoff_package": handoff or {}},
        )

    def load_stage_input(self, stage_id: str) -> Dict[str, Any]:
        return self._load_package(stage_id, "input")

    def load_stage_output(self, stage_id: str) -> Dict[str, Any]:
        return self._load_package(stage_id, "output")

    def handoff_latest_output_to_next(self, stage_id: str, *, max_items: int | None = None) -> ServiceResult:
        output = self.load_stage_output(stage_id)
        if not output:
            return ServiceResult(ok=False, status="missing", message="Ingen output-pakke aa sende videre.", data={})
        target = next_stage_id(stage_id)
        if not target:
            return ServiceResult(ok=False, status="no_next_stage", message="Steget har ikke neste steg.", data={"output_package": output})
        return self.save_stage_input(
            target,
            output.get("candidates") or [],
            origin_stage_id=stage_id,
            source_label=f"Fra {output.get('stage_label') or stage_id}",
            source_package_id=str(output.get("package_id") or ""),
            context={"manual_handoff": True},
            max_items=max_items,
        )

    def stage_status(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for idx, stage in enumerate(STAGE_ORDER, start=1):
            inp = self.load_stage_input(stage.stage_id)
            out = self.load_stage_output(stage.stage_id)
            input_count = int(inp.get("candidate_count") or 0)
            output_count = int(out.get("candidate_count") or 0)
            if input_count == 0 and output_count > 0 and stage.stage_id in {"portfolio_analysis", "paper_trading"}:
                input_count = output_count
            if output_count > 0:
                status = "ferdig"
            elif out and input_count > 0:
                status = "ingen treff - input kan sendes videre"
            elif input_count > 0:
                status = "klar til kjoring"
            elif out:
                status = "ferdig uten kandidater"
            else:
                status = "venter"
            rows.append({
                "nr": idx,
                "stage_id": stage.stage_id,
                "steg": stage.label,
                "formaal": stage.purpose,
                "input": input_count,
                "output": output_count,
                "status": status,
                "sist_input": inp.get("generated_at") or "",
                "sist_output": out.get("generated_at") or "",
                "neste": STAGES_BY_ID.get(stage.next_stage_id).label if stage.next_stage_id in STAGES_BY_ID else "",
                "auto_run": False,
            })
        return rows

    def candidates_for_stage(self, stage_id: str, *, prefer_output: bool = False) -> List[Dict[str, Any]]:
        first = self.load_stage_output(stage_id) if prefer_output else self.load_stage_input(stage_id)
        second = self.load_stage_input(stage_id) if prefer_output else self.load_stage_output(stage_id)
        package = first or second
        return [dict(row) for row in package.get("candidates") or [] if isinstance(row, Mapping)]


def get_analysis_pipeline_service(state_service=None, storage_service=None) -> AnalysisPipelineService:
    return AnalysisPipelineService(state_service=state_service, storage_service=storage_service)


__all__ = [
    "ANALYSIS_PIPELINE_VERSION",
    "AnalysisPipelineService",
    "PIPELINE_INPUTS_STATE_KEY",
    "PIPELINE_LATEST_INPUT_KEY",
    "PIPELINE_LATEST_OUTPUT_KEY",
    "PIPELINE_OUTPUTS_STATE_KEY",
    "PIPELINE_PENDING_NAV_KEY",
    "STAGE_ORDER",
    "STAGES_BY_ID",
    "STAGE_DEFAULT_WIDGETS",
    "STAGE_GROUPS",
    "STAGE_PANEL_LABELS",
    "get_analysis_pipeline_service",
    "next_stage_id",
    "normalize_candidate_rows",
    "previous_stage_id",
    "stage_definitions",
    "stage_number",
    "stage_wizard_info",
    "standard_report_outline",
]

