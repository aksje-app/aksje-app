from unittest.mock import MagicMock

from ui.simulation_restart import render


def test_nok_chart_has_a_temporal_axis_and_no_touch_zoom_or_tooltip():
    st = MagicMock()
    st.text_input.return_value = "nok-demo"
    model = {
        "pointer": {"period_id": "nok-demo"},
        "source_control": "RUNNING",
        "data": {
            "period_id": "nok-demo",
            "family": "super_portfolio",
            "historical_results": "Arkivert",
            "prior_learning": "Bevart",
            "start_at": "2026-10-25T01:51:18+00:00",
            "account": {
                "status": "ACTIVE",
                "new_period": {
                    "start_at": "2026-10-25T01:51:18+00:00",
                    "opening_nav_nok": 1_000_000,
                    "cash_nok": 837_369.41,
                    "positions": {},
                    "trades": [],
                    "realized_pnl_nok": -17_966.09,
                    "unrealized_pnl_nok": 3_088.34,
                    "costs_nok": {"fx_cost_nok": 10_498.52},
                    "period_net_pnl_nok": -14_877.75,
                    "verification": {
                        "verified_nav": 985_122.25,
                        "verified_net_return_pct": -1.4878,
                    },
                },
            },
            "nav_history": [
                {"at": "2026-10-25T01:51:18+00:00", "nav_nok": 1_000_000},
                {"at": "2026-11-20T08:19:41.443947Z", "nav_nok": 982_110.55},
            ],
        },
    }
    render(st, "super_portfolio", ui_model=model)

    assert st.altair_chart.call_count == 1
    spec = st.altair_chart.call_args.args[0].to_dict()
    assert spec["encoding"]["x"]["type"] == "temporal"
    assert spec["encoding"]["y"]["scale"]["zero"] is False
    assert spec["mark"]["tooltip"] is False
    assert "params" not in spec
    rows = next(iter(spec["datasets"].values()))
    assert [row["nav_nok"] for row in rows] == [1_000_000, 982_110.55]
