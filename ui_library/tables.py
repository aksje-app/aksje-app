from __future__ import annotations

from typing import Any


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
