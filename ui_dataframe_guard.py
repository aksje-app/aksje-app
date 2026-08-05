"""Arrow-safe Streamlit dataframe rendering.

Only ambiguous object columns are normalised. Numeric columns containing blank
strings become numeric with missing values, while genuinely mixed columns are
converted to strings. The wrapper is idempotent and leaves non-DataFrame inputs
untouched.
"""
from __future__ import annotations

from numbers import Number
from typing import Any


def arrow_safe_dataframe(data: Any) -> Any:
    try:
        import pandas as pd
    except Exception:
        return data
    if not isinstance(data, pd.DataFrame):
        return data
    frame = data.copy()
    for column in frame.columns:
        series = frame[column]
        if str(series.dtype) != "object":
            continue
        values = list(series)
        meaningful = [value for value in values if value not in (None, "")]
        if not meaningful:
            frame[column] = series.where(series != "", None)
            continue
        numeric_like = []
        non_numeric = []
        for value in meaningful:
            if isinstance(value, bool):
                non_numeric.append(value)
                continue
            if isinstance(value, Number):
                numeric_like.append(value)
                continue
            try:
                float(str(value).strip().replace(",", "."))
                numeric_like.append(value)
            except (TypeError, ValueError):
                non_numeric.append(value)
        if numeric_like and not non_numeric:
            cleaned = series.replace("", None)
            frame[column] = pd.to_numeric(cleaned, errors="coerce")
        elif numeric_like and non_numeric:
            frame[column] = series.map(lambda value: "" if value is None else str(value))
    return frame


def install_streamlit_dataframe_guard(st: Any) -> None:
    if bool(getattr(st, "_ai_arrow_dataframe_guard_v19220_rc15", False)):
        return
    original = st.dataframe

    def guarded(data: Any = None, *args: Any, **kwargs: Any):
        return original(arrow_safe_dataframe(data), *args, **kwargs)

    st.dataframe = guarded
    st._ai_arrow_dataframe_guard_v19220_rc15 = True
