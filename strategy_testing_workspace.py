from __future__ import annotations
import streamlit as st
try:
    from app import render_strategy_backtest as _app_render_strategy_backtest
except Exception:
    _app_render_strategy_backtest=None

try:
    from strategy_test_pro import render_strategy_test_pro as _strategy_test_pro_render_strategy_test_pro
except Exception:
    _strategy_test_pro_render_strategy_test_pro=None


def render_strategy_testing_workspace(ticker: str = "AAPL") -> None:
    st.markdown("### 🧪 Strategi-test / historisk simulering")
    st.caption("Samlet Testing & Learning-område. Strategi-test er beslutningsstøtte og legger ikke ordre.")
    rendered = []
    failures = []

    if _app_render_strategy_backtest is not None:
        try:
            _app_render_strategy_backtest()
            rendered.append("render_strategy_backtest")
        except TypeError:
            try:
                _app_render_strategy_backtest(ticker=ticker)
                rendered.append("render_strategy_backtest")
            except Exception as exc:
                failures.append("render_strategy_backtest: " + str(exc))
        except Exception as exc:
            failures.append("render_strategy_backtest: " + str(exc))

    if _strategy_test_pro_render_strategy_test_pro is not None:
        try:
            _strategy_test_pro_render_strategy_test_pro()
            rendered.append("render_strategy_test_pro")
        except TypeError:
            try:
                _strategy_test_pro_render_strategy_test_pro(ticker=ticker)
                rendered.append("render_strategy_test_pro")
            except Exception as exc:
                failures.append("render_strategy_test_pro: " + str(exc))
        except Exception as exc:
            failures.append("render_strategy_test_pro: " + str(exc))

    if rendered:
        st.success("Aktive moduler vist: " + ", ".join(rendered))
    else:
        st.warning("Ingen aktiv strategi-renderer ble vist. Området er klargjort, men mangler aktiv renderer.")

    if failures:
        with st.expander("Tekniske detaljer / renderer-feil", expanded=False):
            for failure in failures:
                st.write(failure)

    st.markdown("#### Testing & Learning status")
    rows = [
        {"Område": "Strategi-test / historisk simulering", "Status": "✅ Aktiv" if rendered else "🟡 Ikke verifisert / ikke koblet"},
        {"Område": "Strategi-test Pro / optimalisering", "Status": "✅ Aktiv" if any("pro" in x.lower() for x in rendered) else "🟡 Ikke verifisert / ikke koblet"},
        {"Område": "Score-forklaring", "Status": "🟡 Ikke verifisert / ikke koblet"},
        {"Område": "Prognose vs faktisk", "Status": "🟡 Ikke verifisert / ikke koblet"},
        {"Område": "Backtest-læring", "Status": "✅ Aktiv"},
        {"Område": "Trefferate og learning history", "Status": "✅ Aktiv"},
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.info("Punkter merket 🟡 vises ikke som ferdige før de faktisk er koblet og verifisert.")
