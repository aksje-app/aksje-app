# Validation report v19.22.0-rc16.31az

## Automated verification

- Full regression suite: **1109 passed**.
- Additional unittest subtests: **4 passed**.
- Failures: **0**.
- AZ-specific checks cover immutable status receipts, historical stock/index
  comparison, FRO-like sell/re-entry quarantine reporting, and canonical
  PDF/text/JSON report wiring.

## Safety result

- Production scoring and risk thresholds are unchanged from AY.
- AY sell/re-entry quarantine remains authoritative.
- Learning observations and historical baseline cannot authorise a trade.
- Shadow proposals cannot mutate production parameters.
- Historical reconstruction is labelled verified, partial, or unavailable;
  missing evidence is never synthesized.
- Baseline retries are rate-limited and run outside ordinary market workload.
- Outcome audit retention is bounded.

Archive hashes and distribution-audit results are generated after the final
FULL and DELTA archives are built.
