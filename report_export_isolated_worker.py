"""Killable, offline subprocess for one public report package."""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 4:
        return 64
    input_path, output_path, error_path = map(Path, sys.argv[1:])
    try:
        from report_replay_export import _build_public_report_artifacts_inline

        run = json.loads(input_path.read_text(encoding="utf-8"))
        built = _build_public_report_artifacts_inline(run)
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("clean_run.json", json.dumps(built["clean_run"], ensure_ascii=False, sort_keys=True))
            archive.writestr("report.json", built["report_json"])
            archive.writestr("report.txt", built["report_txt"])
            archive.writestr("report.pdf", built["report_pdf"])
            archive.writestr("audit.json", json.dumps(built["audit"], ensure_ascii=False, sort_keys=True))
            archive.writestr("replay_result.json", json.dumps(built["replay_result"], ensure_ascii=False, sort_keys=True))
            archive.writestr("meta.json", json.dumps({
                "replay_level": built["replay_level"],
                "missing": built["missing"],
            }, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        error_path.write_text(json.dumps({"error": str(exc)}, ensure_ascii=False), encoding="utf-8")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
