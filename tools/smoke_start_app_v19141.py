"""Safe end-to-end startup smoke test for the Render stabilization service.

Run from the repository root:
    python tools/smoke_start_app_v19141.py

The script starts Streamlit on a temporary local port, waits for the normal
health route and root page, then stops the child process. It uses isolated
local runtime storage and disables paper trading.
"""
from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return int(response.status), response.read(4096).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(4096).decode("utf-8", errors="replace")


def main() -> int:
    port = _free_port()
    with tempfile.TemporaryDirectory(prefix="aksje-app-startup-") as tmp:
        env = os.environ.copy()
        env.update(
            {
                "APP_RUNTIME_ROOT": str(Path(tmp) / ".app_runtime"),
                "STORAGE_MODE": "local",
                "ALLOW_LOCAL_STORAGE_FALLBACK": "true",
                "PAPER_TRADING_ENABLED": "false",
                "STREAMLIT_SERVER_HEADLESS": "true",
            }
        )
        command = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.headless=true",
            f"--server.port={port}",
            "--server.address=127.0.0.1",
        ]
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.time() + 75
        last_status: tuple[int, str] | None = None
        try:
            while time.time() < deadline:
                if process.poll() is not None:
                    output = process.stdout.read() if process.stdout else ""
                    print(output)
                    return process.returncode or 1
                try:
                    health = _get(f"http://127.0.0.1:{port}/_stcore/health")
                    root = _get(f"http://127.0.0.1:{port}/")
                    last_status = (health[0], root[0])
                    if health[0] == 200 and root[0] == 200:
                        print("Startup smoke test OK: health=200, root=200")
                        return 0
                except OSError:
                    pass
                time.sleep(1)
            print(f"Startup smoke test timed out; last status={last_status}")
            return 1
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
