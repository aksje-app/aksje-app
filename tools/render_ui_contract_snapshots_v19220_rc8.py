from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from ui_layout_contracts import REFERENCE_WIDTHS, currency_runtime_summary_html, currency_status_html


def build_html() -> str:
    cards = [
        ("Valutapar", "BRL/NOK", "Yahoo Finance · BRLNOK=X"),
        ("Siste kurs", "1,87", "Ferske data (2 min)"),
        ("Nedre grense", "1,80", "Status: innenfor"),
        ("Øvre grense", "2,05", "Neste kontroll om 5 min"),
    ]
    currency = currency_status_html(cards)
    runtime = currency_runtime_summary_html(
        title="Automatisk valutakontroll er aktiv",
        quote_time="04.08.2026 18:48:12 (Europe/Oslo)",
        checked_time="04.08.2026 18:48:20 (Europe/Oslo)",
        next_time="04.08.2026 18:53:20 (Europe/Oslo)",
    )
    return f"""<!doctype html>
<html lang='nb'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<style>
html,body{{margin:0;background:#071426;color:#f4f7fb;font-family:Arial,sans-serif;}}
main{{max-width:1180px;margin:0 auto;padding:18px;}}
h1{{font-size:1.45rem;margin:.25rem 0 1rem;}}
.section{{border:1px solid rgba(145,166,200,.28);border-radius:15px;padding:14px;margin:0 0 16px;background:#0b1a30;}}
.banner-off{{display:none!important;height:0!important;min-height:0!important;margin:0!important;padding:0!important;overflow:hidden!important;}}
.banner-on{{height:90px;border:1px solid #30466d;border-radius:12px;display:flex;align-items:center;padding:0 14px;margin-bottom:16px;}}
.diag{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;}}
.diag>div{{border:1px solid #2c4167;border-radius:11px;padding:11px;overflow-wrap:anywhere;}}
</style></head><body><main>
<h1>RC8 visuell kontrakt</h1>
<div id='banner-off' class='banner-off' aria-hidden='true'></div>
<div class='section'><h2>Valutavarsler</h2>{currency}<div class='section'>{runtime}</div></div>
<div class='section'><h2>Driftsdiagnose</h2><div class='diag'><div>Program<br><b>v19.22.0-rc8</b></div><div>Aktiv rute<br><b>currency_alerts</b></div><div>Scheduler<br><b>AKTIV</b></div><div>Tidssone<br><b>Europe/Oslo</b></div></div></div>
</main></body></html>"""


def render(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    html_path = output / "ui_contract_rc8.html"
    html_path.write_text(build_html(), encoding="utf-8")
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path="/usr/bin/chromium", args=["--no-sandbox"])
        for width in REFERENCE_WIDTHS:
            page = browser.new_page(viewport={"width": width, "height": 1000}, device_scale_factor=1)
            page.set_content(html_path.read_text(encoding="utf-8"), wait_until="load")
            page.wait_for_timeout(120)
            metrics = page.evaluate("""() => ({
              viewport: window.innerWidth,
              scrollWidth: document.documentElement.scrollWidth,
              bannerHeight: document.getElementById('banner-off').getBoundingClientRect().height,
              cardCount: document.querySelectorAll('.fx-status-card-v19220rc8').length,
              overflowNodes: [...document.querySelectorAll('body *')].filter(el => el.scrollWidth > el.clientWidth + 1).map(el => el.className || el.tagName).slice(0,20)
            })""")
            screenshot = output / f"ui_contract_{width}px.png"
            page.screenshot(path=str(screenshot), full_page=True)
            metrics["width"] = width
            metrics["screenshot"] = screenshot.name
            metrics["ok"] = metrics["scrollWidth"] <= metrics["viewport"] and metrics["bannerHeight"] == 0 and metrics["cardCount"] == 4
            results.append(metrics)
            page.close()
        browser.close()
    report = {"version": "v19.22.0-rc8", "reference_widths": list(REFERENCE_WIDTHS), "results": results, "ok": all(r["ok"] for r in results)}
    (output / "UI_LAYOUT_VALIDATION_v19.22.0_RC8.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = render(args.output)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
