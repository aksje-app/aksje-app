# v18.5.84 UX Stability Batch B

## 4. Global update responsive fix
- Added hard CSS override for the `v18581-global-toolbar` / status / action button.
- Removed desktop text collision risk by allowing wrapping, using `clamp()` font sizing, clearing floats, and preventing hidden overflow.
- Mobile keeps the same blue control, but stacks cleanly under 900px.

## 5. Toast/status overlap
- Replaced persistent success alert after Global oppdatering with `st.toast()` when available, with `st.info()` fallback.
- Added CSS so Streamlit alerts remain in normal document flow and do not overlay buttons.
- Added spacing/clear rules around pending state box and global toolbar.

## 6. State consistency
- Clarified manual-mode text: local UI choices are local until Global oppdatering; heavy analysis uses last approved dataset.
- Global status now remains the single visible truth for: running, pending, and clean state.

## Notes
This batch is intentionally UI/state-stability only. No analysis engines or scoring logic were changed.
