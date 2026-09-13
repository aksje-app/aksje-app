"""Retired compatibility tombstone for delta deployments.

The temporary Jeep Commander module was removed in RC16.31cr. This file
contains no network, scheduler, notification or storage functionality. A full
deployment does not include it; it only overwrites an older active module when
the small delta package is applied over an existing installation.
"""


def run_due_monitor(*args, **kwargs):
    return {"state": "REMOVED", "checked": 0, "sent": 0}


def render_streamlit_module(st):
    st.info("Jeep Commander 2.2-modulen er fjernet i RC16.31cr.")
