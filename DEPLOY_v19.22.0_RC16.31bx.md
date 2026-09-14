# Deploy - RC16.31bx

1. Apply the clean DELTA to the repository root and push one commit.
2. Wait until web, scheduler and paper-scanner show the same RC16.31bx version and commit.
3. Start one manual **Utkast** from a desktop browser and confirm the first click immediately changes to `STARTING / 0%` and then updates without F5.
4. Confirm a completed run shows one **Rapportfiler** block containing Standard PDF, Technical PDF, JSON and Diagnostic ZIP, plus the optional complete ZIP.
5. Open `Vis hvorfor kandidater ikke ble BUY` and confirm `Første blocker` is fully readable/wrapped.
6. Confirm baseline progress (for example `short 16/80`) is explicitly described as an intermediate deep-analysis control set.
7. For the BW Norway-universe acceptance, require `NORWAY_UNIVERSE status=OFFICIAL_LIVE`, an authoritative master and a plausible split across XOSL/MERK/XOAS. Do not accept the 82 fallback as complete.
8. Confirm no `Duplikat kandidat i kanonisk rapportmodell` crash occurs. If duplicate ingress occurs, expect a `CANONICAL_DEDUP ticker=...` log and successful continuation.
9. Observe at least the next normal 08:00/14:00/22:00 report before production-ready status is declared.
