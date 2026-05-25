# Clean work_d manifest v18.6.3bn

Created from `old_work_d` as a clean GitHub upload folder.

Included:
- active app/runtime Python modules from the root of `old_work_d`
- `services/` without Python cache files
- active pytest suite selected by `pytest.ini`
- runtime/deploy config: `requirements.txt`, `runtime.txt`, `render.yaml`, `.gitignore`
- current project notes needed for this version
- empty `data/` and `storage/` placeholders via `.gitkeep`

Excluded:
- `.env` and local secrets
- runtime user/session files such as `app_users.json` and `remember_tokens.json`
- local app data under `data/` and `storage/`
- Streamlit logs, QA screenshots, cache folders and patch staging folders
- old v18.5-era tests/docs outside the active `pytest.ini` suite

Validation target:
- run `python -m pytest -q` from this folder before uploading to GitHub.
