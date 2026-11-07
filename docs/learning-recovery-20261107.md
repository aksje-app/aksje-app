# Three historical learning streams: recovery and evidence

The user confirmed the three streams: AUTONOMY, SUPER_PORTFOLIO and
AUTONOMY_UNIVERSE. Production inspection on 7 November found:

| Stream | Verified frames | Last archived input | Forward dates |
| --- | ---: | --- | ---: |
| Autonomi | 70 | 29 October | 11 |
| Superporteføljen | 32 | 30 October | 13 |
| Whole configured input universe | 33 | 29 October | Capture only |

The universe stream preserves inputs for research. It does not have a separate
forward trading engine. The first two engines each have three frozen variants
(reference, threshold minus two, threshold plus two). Neither three streams nor
three variants is proof of three validated strategies.

## Confirmed blockers

The shared immutable history index consumed 134,155,087 bytes of its hard
134,217,728-byte budget, had 135 records and 105 reported gaps, and was marked
STORAGE_BUDGET_REACHED. New frames were refused; no old frames were deleted.
The daily watchdog only checked registration/evaluation job invocations and
missed this stopped input stream. Registrations may create zero observations.

The 91 price-observation cohorts already all have 1/5/20-trading-day benchmark
measurements, while none has completed 60 days. The notification hid these
intermediate results behind a zero count of fully matured observations and
the separate strategy-position gate.

Measured 20-day group means, descriptive price returns rather than net trades:

| Group | Observations | Return | Excess over benchmark |
| --- | ---: | ---: | ---: |
| Moderate | 30 | +0.1298% | +1.5517 percentage points |
| Near threshold | 30 | -1.2764% | -0.5666 percentage points |
| Matched control | 30 | +0.0265% | +0.6847 percentage points |
| Strict | 1 | -9.4937% | -11.2391 percentage points |

These observations span older application cohorts and overlapping inputs.
They do not prove improved current-strategy net performance or justify any
production parameter change. The current learning portfolio has 73 open and
129 closed positions; only four open and thirteen closed belong to the current
application cohort. None of those thirteen closed positions has 20 recorded
observation days. No closed position has a measured benchmark return in that
portfolio path. Its benchmark collector and strategy identity remain separate
validation work; these fixes do not manufacture missing benchmark values,
merge incompatible cohorts or lower the promotion gates.

The immutable historical baseline is still the 5 September snapshot with
1382 signals, measured only at 1/5 days. It is not current forward progress.
The week-45 report was generated, but its notification was classified routine,
suppressed as in-app-only and then never retried because the report existed.

## Repair

- Increase only the bounded disk archive budget to 256 MiB. This adds at most
  128 MiB to the measured roughly 3.206 GB database on its existing 5 GiB plan.
  The 8 MiB per-frame, bounded batches and worker resource limits stay intact.
  Preserve all existing frame bytes, checksums, records and gap counts.
- A new successful capture clears the active budget stop, retaining old gaps.
  Before a real new capture, report capacity-restored/waiting, not resumed data.
  Retry previously budget-blocked historical imports, not invalid evidence.
  Historical imports remain excluded from forward data.
- Daily reports expose all three streams and their last input dates, forward
  status, actual new-observation/measurement counts and measured sub-horizons.
  Capacity exhaustion, less than 16 MiB remaining, stale streams and failed
  weekly delivery are explicit failures even if job invocations succeed.
- Retry the same weekly report/PDF delivery, without regenerating its analysis,
  at most five attempts with one hour between attempts. Use a learning-report
  category rather than routine, while keeping the notifier's global enable,
  safety and deduplication controls. Preserve explicit no-notification reports.
- An explicit operator repair ID may deliver one corrected daily summary,
  retaining the original daily receipt and deduplicating that repair separately.
  Ordinary scheduler calls never opt into this extra delivery.

This is bounded capacity, not unlimited retention. Further capacity action will
be visible before the new ceiling; historical completeness is never inferred
from a successful restart. The missing 105 captures must not be reconstructed
from today's market/news data.

## Acceptance

Run regression tests and Release Gate on the exact source before main/deploy.
Then verify actual production capture/worker states, immutable old-index
fingerprints and preserved gaps, real weekly Pushover delivery and current
three-stream status. Do not call the strategies validated, manufacture a third
trading engine, or count a weekend as new market-time evidence. Remaining
benchmark/cohort validation limitations must remain visible.
