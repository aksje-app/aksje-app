from __future__ import annotations

from typing import Any
from collections.abc import Callable, Sequence


def render_table(
    st_module,
    data: Any,
    *,
    key: str | None = None,
    height: int | None = None,
    hide_index: bool = True,
    use_container_width: bool = True,
    column_config: dict[str, Any] | None = None,
) -> None:
    """Single compatibility wrapper for read-only tabular output."""
    kwargs: dict[str, Any] = {
        "hide_index": hide_index,
        "use_container_width": use_container_width,
    }
    if key:
        kwargs["key"] = key
    if height:
        kwargs["height"] = height
    if column_config:
        kwargs["column_config"] = column_config
    try:
        st_module.dataframe(data, **kwargs)
    except TypeError:
        kwargs.pop("key", None)
        st_module.dataframe(data, **kwargs)
    except Exception:
        st_module.write(data)

def responsive_records(st_module, rows: Sequence[Any], *, mobile_card: Callable[[Any], str], key: str | None = None) -> None:
    cards="".join(f'<article class="aa-ui-mobile-record">{mobile_card(row)}</article>' for row in rows)
    st_module.markdown(f'<div class="aa-ui-mobile-records">{cards}</div>',unsafe_allow_html=True)
    render_table(st_module,rows,key=key)
