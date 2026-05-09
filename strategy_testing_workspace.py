"""
strategy_testing_workspace.py

v18.5.2
Samler strategi-test, optimalisering og score-forklaring i AI Kontrollsenter -> Testing & Learning.
Ingen auto-trading-kobling.
"""

from __future__ import annotations

import streamlit as st

try:
    from app import render_strategy_backtest as _app_render_strategy_backtest
except Exception:
    _app_render_strategy_backtest = None

try:
    from strategy_test_pro import render_strategy_test_pro as _strategy_test_pro_render_strategy_test_pro
except Exception:
    _strategy_test_pro_render_strategy_test_pro = None


def render_strategy_testing_workspace() -> None:
    """Render strategy testing tools inside AI Control Center."""
    st.markdown("### 🧪 Strategi-test / historisk simulering")
    st.caption("Samlet Testing & Learning-område. Strategi-test er beslutningsstøtte og legger ikke ordre.")

    rendered = 0

    if _app_render_strategy_backtest is not None:
        try:
            _app_render_strategy_backtest()
            rendered += 1
        except TypeError:
            try:
                _app_render_strategy_backtest(ticker="AAPL")
                rendered += 1
            except Exception as exc:
                st.warning("render_strategy_backtest kunne ikke vises: " + str(exc))
        except Exception as exc:
            st.warning("render_strategy_backtest kunne ikke vises: " + str(exc))

    if _strategy_test_pro_render_strategy_test_pro is not None:
        try:
            _strategy_test_pro_render_strategy_test_pro()
            rendered += 1
        except TypeError:
            try:
                _strategy_test_pro_render_strategy_test_pro(ticker="AAPL")
                rendered += 1
            except Exception as exc:
                st.warning("render_strategy_test_pro kunne ikke vises: " + str(exc))
        except Exception as exc:
            st.warning("render_strategy_test_pro kunne ikke vises: " + str(exc))

    if rendered == 0:
        st.info("Fant ingen aktiv strategi-renderer å vise. Området er klargjort for strategi-testmodulen.")
        st.markdown(
            """
            **Testing & Learning samler:**
            - Strategi-test / historisk simulering
            - Strategi-test Pro / optimalisering
            - Score-forklaring
            - Prognose vs faktisk
            - Backtest-læring
            - Trefferate og learning history
            """
        )
