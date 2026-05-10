from forecast_engine import build_all_horizons
from forecast_store import get_forecast_vs_actual_series


def test_manual_list_widget_key_not_mutated_after_instantiation():
    src = open('analysis_universe_ai.py', encoding='utf-8').read()
    forbidden = 'st.session_state["ai_universe_manual_list_draft_v18517"] ='
    assert forbidden not in src
    assert 'ai_universe_manual_list_saved_v18525' in src


def test_forecast_actual_history_never_extends_into_future():
    prices = [100 + i for i in range(90)]
    payload = {'ticker': 'AAPL', 'horizons': build_all_horizons('AAPL', prices)}
    series = get_forecast_vs_actual_series(payload, prices[-40:], '1m')

    assert series['today_label'] in series['forecast_x']
    assert series['actual_history_x'][-1] == series['today_label']
    assert series['forecast_x'][0] == series['today_label']
    assert series['actual_has_future_values'] is False

    future_start = series['future_start_index']
    assert all(value is None for value in series['actual'][future_start:])
    assert len(series['forecast_base']) == len(series['forecast_x'])
    assert len(series['forecast_bull']) == len(series['forecast_x'])
    assert len(series['forecast_bear']) == len(series['forecast_x'])
