import logging

import scheduled_runner


def test_headless_filter_demotes_only_known_streamlit_bare_mode_warning():
    scheduled_runner._configure_headless_logging()
    factory = logging.getLogRecordFactory()
    bare = factory(
        "streamlit.runtime.scriptrunner_utils.script_run_context", logging.WARNING,
        __file__, 1, "Thread MainThread: missing ScriptRunContext!", (), None,
    )
    real = factory("application", logging.WARNING, __file__, 1, "real warning", (), None)
    assert bare.levelno == logging.DEBUG
    assert real.levelno == logging.WARNING
