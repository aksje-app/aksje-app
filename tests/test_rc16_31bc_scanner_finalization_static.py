from pathlib import Path


def test_scanner_resume_boundary_is_finalization_not_ticker_n_plus_one():
    source = Path("scanner_worker.py").read_text(encoding="utf-8")
    assert "if start_index >= len(tickers):" in source
    assert "Gjenopptar sluttbehandling etter" in source
    assert "ingen ny ticker kjøres" in source
    assert '"phase": "FINALIZING"' in source
    assert '"next_index": len(tickers)' in source


def test_snapshot_identity_is_persisted_through_checkpoint_resume():
    source = Path("scanner_worker.py").read_text(encoding="utf-8")
    assert 'checkpoint.get("market_snapshot_id")' in source
    assert source.count('"market_snapshot_id": market_snapshot_id') >= 3


def test_learning_maintenance_cannot_delay_paper_scanner():
    source = Path("scheduled_runner.py").read_text(encoding="utf-8")
    assert source.index("scheduled_runner:before_paper_scanner") < source.index(
        "scheduled_runner:before_learning_observations"
    )
