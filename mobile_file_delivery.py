"""One durable, mobile-first delivery surface for generated application files."""
from __future__ import annotations

from html import escape
import hashlib
from typing import Any


def render_mobile_file_delivery(
    st: Any,
    *,
    url: str,
    filename: str,
    label: str,
    mime: str,
    data: bytes | None = None,
    key: str,
    return_url: str = "/",
    instance_key: str = "",
) -> None:
    """Render open, download, copy, share and return without losing the app.

    The URL must point at a durable static/public resource.  The ordinary
    Streamlit download control remains a fallback, but is never the only path.
    """
    safe_url = escape(str(url or ""), quote=True)
    safe_name = escape(str(filename or "nedlasting"), quote=True)
    safe_label = escape(str(label or "Last ned"))
    safe_return = escape(str(return_url or "/"), quote=True)
    st.markdown(
        '<div data-testid="mobile-file-delivery" style="display:grid;grid-template-columns:1fr 1fr;gap:.55rem;margin:.35rem 0">'
        f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer" '
        'style="grid-column:1/-1;display:block;text-align:center;padding:.75rem;border-radius:.55rem;'
        'background:#0284c7;color:white;text-decoration:none;font-weight:800">'
        f'{safe_label}</a>'
        f'<a href="{safe_url}" download="{safe_name}" target="_blank" rel="noopener noreferrer" '
        'style="display:block;text-align:center;padding:.65rem;border:1px solid #38bdf8;border-radius:.5rem;'
        'color:inherit;text-decoration:none;font-weight:700">Last ned fil</a>'
        f'<a href="{safe_return}" target="_self" '
        'style="display:block;text-align:center;padding:.65rem;border:1px solid #2dd4bf;border-radius:.5rem;'
        'color:inherit;text-decoration:none;font-weight:700">← Tilbake til programmet</a>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ``st.code`` has Streamlit's native copy control and works in the normal
    # app document instead of a sandboxed component.  Opening the durable file
    # exposes the phone/browser's ordinary Share action without replacing the
    # original app tab.
    st.caption("Kopier varig lenke med kopiknappen, eller åpne filen og bruk telefonens delingsmeny.")
    st.code(str(url or ""), language=None)

    if data is not None:
        # The same report can legitimately be visible in both "Siste rapport"
        # and the archive.  Scope the native widget to its panel so Streamlit
        # never receives two identical keys in one render pass.
        identity = "|".join((str(key), str(instance_key), str(url), str(filename)))
        fallback_key = f"{key}_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:12]}_fallback"
        with st.expander("Reserve: direkte nedlasting", expanded=False):
            st.download_button(
                "Last ned direkte",
                data=bytes(data),
                file_name=str(filename or "nedlasting"),
                mime=str(mime or "application/octet-stream"),
                key=fallback_key,
                width="stretch",
            )


__all__ = ["render_mobile_file_delivery"]
