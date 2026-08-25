from pathlib import Path
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_render_has_one_cron_and_scanner_uses_2gb_scheduler():
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    cron = [service for service in blueprint["services"] if service["type"] == "cron"]
    assert len(cron) == 1
    service = cron[0]
    assert service["name"] == "aksje-app-report-scheduler"
    assert service["plan"] == "standard"
    assert service["startCommand"] == "python scheduled_runner.py"
    env = {row["key"]: row.get("value") for row in service["envVars"]}
    assert env["PAPER_TRADING_ENABLED"] == "true"
    assert env["SCANNER_MEMORY_SOFT_LIMIT_MB"] == "1700"
    assert env["SCANNER_MAX_TICKERS"] == "30"


def test_scheduler_orders_reports_before_scanner_and_avoids_duplicate_fx():
    source = (ROOT / "scheduled_runner.py").read_text(encoding="utf-8")
    assert source.index("run_scheduler_cycle") < source.index("run_paper_scanner")
    assert "check_currency_alerts=False" in source
    assert "SEQUENTIAL_SHARED_2GB_SCHEDULER" in source


def test_scanner_default_still_checks_fx_for_direct_manual_runs():
    import scanner_worker

    with patch.object(scanner_worker, "run_coordinated", return_value=7) as coordinated:
        assert scanner_worker.run_once(force=True) == 7
        callback = coordinated.call_args.args[0]
        with patch.object(scanner_worker, "_run_once_impl", return_value=3) as implementation:
            assert callback(force=True) == 3
            implementation.assert_called_once_with(force=True, check_currency_alerts=True)


def test_scheduler_call_disables_second_fx_check():
    import scanner_worker

    with patch.object(scanner_worker, "run_coordinated", return_value=0) as coordinated:
        scanner_worker.run_once(force=False, check_currency_alerts=False)
        callback = coordinated.call_args.args[0]
        with patch.object(scanner_worker, "_run_once_impl", return_value=0) as implementation:
            callback(force=False)
            implementation.assert_called_once_with(force=False, check_currency_alerts=False)
