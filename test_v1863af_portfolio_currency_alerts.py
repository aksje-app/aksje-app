from pathlib import Path
import py_compile


for name in ["app.py", "app_version.py"]:
    py_compile.compile(name, doraise=True)

app = Path("app.py").read_text(encoding="utf-8", errors="ignore")
version = Path("app_version.py").read_text(encoding="utf-8", errors="ignore")

assert 'APP_VERSION = "v18.6.12"' in version
assert "render_paper_portfolio_control_center_v1863af" in app
assert "render_currency_alerts_control_center_v1863af" in app
assert "currency_alerts_v1863af" in app
assert "BRL/NOK" in app and "BRLNOK=X" in app
assert "Sjekk hvert" in app
assert "Varselpause" in app
assert "check_interval_minutes" in app
assert "cooldown_minutes" in app
assert "Hent kurs nå" in app
assert "Sjekk valutagrense nå" in app
assert "Send Pushover-test" in app
assert "_pushover_runtime_status_v1864u" in app
assert "Status nå" in app
assert "Varseloppsett" in app
assert "send_pushover_alert" in app




















