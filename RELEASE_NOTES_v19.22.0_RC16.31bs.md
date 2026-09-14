# RC16.31bs – Evidence Coverage Semantics

RC16.31bs corrects the public meaning of the report metric that previously showed `evidence ready / all candidates`, for example `13/73 · 18%`.

## Changed

- Keeps the legacy whole-population ratio in JSON for backward compatibility, but no longer uses it as the report-facing quality score.
- Adds `candidate_evidence_controlled_count` from stage-3 evidence control.
- Adds `candidate_evidence_success_rate = evidence_ready / evidence_controlled`.
- Adds `candidate_evidence_not_prioritized_count = candidate_total - evidence_controlled`.
- The PDF card now reads `Evidensklar etter kontroll` and uses the controlled population as denominator.
- The PDF explanatory text states how many were evidence-controlled, how many became evidence-ready, and how many were not prioritized for full evidence control.
- Text reports and public channel projection carry the same semantics.
- No buy threshold, risk threshold, portfolio rule, Fresh Trend scoring, universe rule, or Paper Trade rule is changed.

## Example

A run with 73 candidates, 20 evidence-controlled and 13 evidence-ready now presents:

- Evidenskontrollert: 20/73
- Evidensklar etter kontroll: 13/20 = 65%
- Ikke prioritert til full evidenskontroll: 53

The former `13/73 = 17.8%` remains available only as a compatibility field, not as the report-facing quality measure.
