"""Run the real Streamlit server with a health-checked deployment heartbeat.

The cron's strict peer check must not depend on an open browser session.
No app requests, analysis, authentication or trading are performed by this loop.
"""
from __future__ import annotations
import logging
import os
import sys
import threading
from urllib.request import ProxyHandler, Request, build_opener


def publish_healthy_identity(port: int) -> bool:
    # Only loopback is permitted here. Do not send internal health probes via
    # an outbound proxy or mistake a public service response for this process.
    opener = build_opener(ProxyHandler({}))
    with opener.open(Request(f'http://127.0.0.1:{port}/_stcore/health'), timeout=2) as response:
        if response.status != 200:
            return False
    from runtime_identity import publish_runtime_identity
    identity = publish_runtime_identity('web')
    logging.info('WEB_RUNTIME_HEARTBEAT commit=%s version=%s', identity['commit'], identity['version'])
    return True


def heartbeat(stop: threading.Event, port: int) -> None:
    delay = 1
    while not stop.wait(delay):
        try:
            healthy = publish_healthy_identity(port)
            delay = 60 if healthy else 5
        except Exception as exc:
            # A failed probe never renews the identity or weakens the cron gate.
            logging.warning('Web runtime heartbeat not published: %s', type(exc).__name__)
            delay = 5


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    port = int(os.getenv('PORT') or '10000')
    if not 1 <= port <= 65535:
        raise ValueError('Invalid Streamlit port')
    stop = threading.Event()
    thread = threading.Thread(target=heartbeat, args=(stop,port), name='web-runtime-heartbeat', daemon=True)
    thread.start()
    try:
        from streamlit.web.cli import main as streamlit_main
        sys.argv = ['streamlit','run','app.py','--server.address=0.0.0.0',f'--server.port={port}']
        streamlit_main()
    finally:
        stop.set()
        thread.join(timeout=3)


if __name__ == '__main__':
    main()
