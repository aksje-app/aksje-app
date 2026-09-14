# Release Notes - RC16.31ca

## Report Package and Learning Health Closure

This release closes the remaining concrete report-delivery and learning-health defects observed in RC16.31bz.

### Changes
- The single-report ZIP now includes the canonical standard PDF, canonical technical PDF and canonical JSON. For manual/background runs it also includes the durable diagnostic ZIP when that diagnostic exists.
- The ZIP manifest records explicit artifact roles and whether a diagnostic bundle was available.
- The current-report UI now uses the same unified **Rapportfiler** block as archived reports instead of the older duplicate download/package controls.
- Exchange names are hydrated consistently in the recommendation, observation and rejection tables from the canonical Norway candidate metadata.
- A newly registered learning observation with no trading session after its entry date is now `AWAITING_NEXT_TRADING_DAY`, not `MISSING_SERIES`. This prevents a normal overnight wait from degrading the whole learning status.
- RC16.31bz fine-grained progress and monotonic progress behavior are preserved unchanged.

### Intentionally unchanged
- BUY thresholds, investment scoring, risk limits and portfolio rules.
- Norway master-universe logic and 294-share coverage behavior.
- Fresh Trend logic and candidate-selection budgets.
- Evidence-readiness gates are not loosened. Missing evidence remains missing rather than being reclassified as valid.
