from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_version_bumped_to_bq():
    src = read("app_version.py")
    assert 'APP_VERSION = "v19.22.0-rc16.31bq"' in src
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.31bp"' in src


def test_runtime_memory_exposes_cgroup_breakdown_and_reclaim():
    src = read("runtime_memory.py")
    assert "def _cgroup_memory_stat()" in src
    assert '"/sys/fs/cgroup/memory.reclaim"' in src
    assert "def reclaim_cgroup_memory" in src
    assert "def terminal_memory_cleanup" in src
    assert 'result[f"cgroup_{key}_mb"]' in src


def test_manual_terminal_status_overwrites_stale_failed_progress_event():
    src = read("manual_job_background.py")
    assert '"message": "Hele kjeden er ferdig"' in src
    assert '"status": "COMPLETED"' in src
    assert 'terminal_memory_cleanup(' in src
    assert 'final["resource_telemetry"] = dict(terminal_cleanup.get("final") or {})' in src
    assert 'final["terminal_memory_cleanup"] = terminal_cleanup' in src


def test_market_complete_uses_authoritative_release_and_chain_gates():
    src = read("market_intelligence.py")
    assert 'release_ok_bq = bool((run.get("final_release_gate") or {}).get("ok"))' in src
    assert 'chain_ok_bq = str((run.get("autonomous_chain") or {}).get("status")' in src
    assert 'terminal_ok_bq = release_ok_bq and chain_ok_bq' in src
    assert 'status="COMPLETED" if terminal_ok_bq else "FAILED"' in src


def test_market_runs_terminal_cleanup_before_complete_emit():
    src = read("market_intelligence.py")
    cleanup = src.index('terminal_memory_cleanup(\n            "manual_report_before_complete_emit"')
    complete = src.index('emit(\n        "COMPLETE"', cleanup)
    assert cleanup < complete
    assert '"report:memory_cleanup:before_complete"' in src


def test_scanner_closed_message_is_policy_aware():
    src = read("scanner_worker.py")
    assert "Ingen aktiverte produksjonsmarkeder er åpne" in src
    assert "Andre markeder kan være åpne, men er deaktivert av gjeldende scanner-policy" in src
    assert "⏸ Alle markeder stengt - ingen scanning" not in src


def test_memory_reclaim_does_not_delete_application_files():
    src = read("runtime_memory.py")
    body = src[src.index("def reclaim_cgroup_memory"):src.index("def terminal_memory_cleanup")]
    assert "unlink(" not in body
    assert "remove(" not in body
    assert "rmtree(" not in body
