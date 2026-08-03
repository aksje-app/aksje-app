#!/usr/bin/env python3
"""Validate that a report ZIP contains mutually identifiable PDF and JSON outputs.

This is an automated gate, not a replacement for the final visual page review.
"""
from __future__ import annotations
import argparse, json, re, tempfile, zipfile
from pathlib import Path
from pypdf import PdfReader

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("bundle", type=Path)
    args=ap.parse_args()
    errors=[]
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(args.bundle) as zf:
            zf.extractall(td)
        files=list(Path(td).rglob("*"))
        pdfs=[p for p in files if p.suffix.lower()==".pdf"]
        jsons=[p for p in files if p.suffix.lower()==".json"]
        if len(pdfs)!=1: errors.append(f"Forventet 1 PDF, fant {len(pdfs)}")
        if len(jsons)!=1: errors.append(f"Forventet 1 JSON, fant {len(jsons)}")
        if not errors:
            payload=json.loads(jsons[0].read_text(encoding="utf-8"))
            reader=PdfReader(str(pdfs[0]))
            text="\n".join((page.extract_text() or "") for page in reader.pages)
            report_id=str(payload.get("report_id") or payload.get("id") or "")
            version=str(payload.get("app_version") or payload.get("version") or "")
            if report_id and report_id not in text: errors.append("Rapport-ID fra JSON finnes ikke i PDF-tekst")
            if version and version not in text: errors.append("Appversjon fra JSON finnes ikke i PDF-tekst")
            if len(reader.pages)<2: errors.append("PDF har færre enn 2 sider")
            if not re.search(r"UTKAST|ENDELIG|FULLFØRT", text, re.I): errors.append("Rapportstatus kunne ikke identifiseres i PDF")
            print(json.dumps({"ok":not errors,"pages":len(reader.pages),"report_id":report_id,"version":version,"errors":errors},ensure_ascii=False,indent=2))
    return 1 if errors else 0
if __name__ == "__main__": raise SystemExit(main())
