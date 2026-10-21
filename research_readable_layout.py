"""Isolated mobile-safe text layout for research read-only panels.

Use one HTML block per section to avoid collisions caused by global
Streamlit paragraph/vertical gap density rules.
"""
from html import escape

def lines(st, *values):
    items = "".join(
        '<div style="display:block;position:relative;min-height:1.6em;'
        'height:auto;line-height:1.5;margin:0 0 0.85rem 0;'
        'padding:0;white-space:normal;overflow-wrap:anywhere;">'
        + escape(str(value)) + '</div>'
        for value in values if value is not None
    )
    st.markdown(
        '<section class="research-readable-lines" style="display:flow-root;'
        'height:auto;overflow:visible;padding:0.35rem 0 0.65rem 0;'
        'margin:0.3rem 0 1rem 0;clear:both;">' + items + '</section>',
        unsafe_allow_html=True,
    )
