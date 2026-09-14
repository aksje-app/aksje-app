"""Single execution entry point for durable Super Portfolio jobs."""
from __future__ import annotations

import argparse
import os
import threading
import time
from typing import Any, Mapping

import super_portfolio_jobs as jobs


def _build_pipeline(**kwargs: Any) -> dict[str, Any]:
    from super_portfolio import SuperPortfolioConfig, build_super_portfolio_market_pipeline, load_state

    state = load_state()
    config_data = state.get("config") if isinstance(state.get("config"), Mapping) else {}
    allowed = set(SuperPortfolioConfig.__dataclass_fields__)
    cfg = SuperPortfolioConfig(**{key: value for key, value in config_data.items() if key in allowed})
    return dict(build_super_portfolio_market_pipeline(cfg=cfg, **kwargs) or {})


def _evaluate_pipeline(pipeline: Mapping[str, Any], trigger: str) -> dict[str, Any]:
    if str(trigger or "").upper() == "SCHEDULED":
        # Reuse the established scheduled finalization so benchmark refresh,
        # last-source id, Pushover and audit behavior cannot silently regress.
        from super_portfolio import run_scheduled_shadow_cycle
        return dict(run_scheduled_shadow_cycle(pipeline=pipeline) or {})
    from super_portfolio import evaluate
    return dict(evaluate(pipeline=pipeline, persist=True, rebalance_policy="ANALYZE_ONLY") or {})


def publish_verified_result(job_id: str, execution_token: str, pipeline: Mapping[str, Any]) -> dict[str, Any]:
    current = jobs.get_job(job_id)
    jobs._require_worker(current, job_id, execution_token)
    verification = pipeline.get("verification") if isinstance(pipeline.get("verification"), Mapping) else {}
    if not verification.get("ok"):
        raise RuntimeError("SP worker refused an unverified pipeline")
    outcome = str(pipeline.get("outcome") or "COMPLETED").upper()
    terminal = "DEGRADED" if outcome == "DEGRADED" else "COMPLETED"
    return jobs.update_job(
        job_id, execution_token, state=terminal, outcome=terminal,
        phase="VERIFIED", percent=100, message="SP-vurderingen er ferdig og verifisert",
        final_pipeline_run_id=str(pipeline.get("run_id") or ""), error="",
    )


def _heartbeat_loop(job_id: str, token: str, stop_event: threading.Event) -> None:
    while not stop_event.wait(10):
        try:
            status = jobs.get_job(job_id)
            jobs.update_job(
                job_id, token, heartbeat_at=jobs._now(),
                state=status.get("state") or "RUNNING",
            )
        except Exception:
            return


def run_claimed_job(job_id: str, execution_token: str) -> dict[str, Any]:
    stop_heartbeat = threading.Event()
    heartbeat: threading.Thread | None = None
    try:
        with jobs.worker_execution_lease(job_id, execution_token):
            initial = jobs.get_job(job_id)
            trigger = str(initial.get("trigger") or "MANUAL").upper()
            jobs.update_job(
                job_id, execution_token, state="STARTING", phase="STARTING", percent=1,
                started_at=jobs._now(), worker_pid=os.getpid(),
                worker_process_identity=f"pid:{os.getpid()}", message="Laster SP-komponenter",
                worker_host=str(os.getenv("RENDER_INSTANCE_ID") or os.getenv("HOSTNAME") or ""),
            )
            heartbeat = threading.Thread(
                target=_heartbeat_loop, args=(job_id, execution_token, stop_heartbeat),
                daemon=True, name="sp-heartbeat",
            )
            heartbeat.start()
            jobs.update_job(
                job_id, execution_token, state="RUNNING", phase="START", percent=2,
                message="Starter Super Portfolio-markedsskanning",
            )
            pipeline = _build_pipeline(
                force_refresh=bool(initial.get("force_refresh", True)),
                progress_callback=lambda event: jobs.append_progress(job_id, execution_token, event),
                control_callback=lambda: jobs.control_state(job_id, execution_token),
                checkpoint_callback=lambda checkpoint: jobs.save_checkpoint(job_id, execution_token, checkpoint),
                job_id=job_id,
            )
            if not pipeline.get("candidates"):
                raise RuntimeError("SP-skanningen ga ingen verifiserte kandidater")
            jobs.append_progress(job_id, execution_token, {
                "stage": "PORTFOLIO_EVALUATION", "percent": 99,
                "message": "Bygger rangering og porteføljebeslutninger",
            })
            result = _evaluate_pipeline(pipeline, trigger)
            terminal = publish_verified_result(job_id, execution_token, pipeline)
            return {**terminal, "changes": len(result.get("changes") or [])}
    except Exception as exc:
        if type(exc).__name__ in {"ScanCancelled", "SupersededWorker"}:
            if type(exc).__name__ == "SupersededWorker":
                return jobs.get_job(job_id)
            try:
                return jobs.update_job(
                    job_id, execution_token, state="CANCELLED", outcome="CANCELLED",
                    failure_phase="CONTROL", message="SP-jobben ble stoppet av bruker",
                )
            except Exception:
                return jobs.get_job(job_id)
        try:
            return jobs.update_job(
                job_id, execution_token, state="FAILED", outcome="FAILED",
                failure_type=type(exc).__name__,
                failure_phase=str((jobs.get_job(job_id) or {}).get("phase") or "RUNNING"),
                error=f"{type(exc).__name__}: {str(exc)[:1000]}",
                message="SP-jobben feilet; forrige verifiserte resultat er beholdt",
            )
        except Exception:
            return jobs.get_job(job_id)
    finally:
        stop_heartbeat.set()
        if heartbeat is not None:
            heartbeat.join(timeout=1)
        try:
            from runtime_memory import release_process_memory
            release_process_memory("sp:worker:terminal")
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--execution-token", required=True)
    args = parser.parse_args()
    result = run_claimed_job(args.job_id, args.execution_token)
    return 0 if str(result.get("state") or "") in {"COMPLETED", "DEGRADED", "CANCELLED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
