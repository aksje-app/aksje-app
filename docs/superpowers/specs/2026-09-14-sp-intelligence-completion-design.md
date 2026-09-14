# SP Intelligence Completion Design

## Goal
Complete the remaining SP backlog without changing real-order systems: candidate persistence, regime-aware rebalance thresholds, per-stock data coverage gating, a broader USA discovery universe, and explicit separation between AI advice and Shadow execution.

## Architecture
SP remains an isolated Shadow layer. Market discovery is widened only for SP; the authoritative production universe behavior is not changed. New selection-safety metadata is persisted in SP state/history and participates only in ordinary rebalance decisions; hard-stop behavior remains immediate.

## Candidate persistence
Track consecutive fresh decision runs in which an outside candidate is eligible for the target portfolio. Ordinary challenger replacement requires 2 consecutive qualifying fresh runs by default. Existing positions, emergency hard stops, and first portfolio initialization are not blocked by persistence.

## Regime-aware thresholds
Derive a simple regime bucket from pipeline metadata when available: CALM, NORMAL, STRESSED. CALM increases patience; STRESSED permits faster replacement. Threshold adjustments affect challenger score margin, confidence minimum and persistence-run requirement. Defaults remain conservative when regime data is missing.

## Data coverage gate
Every candidate receives an auditable coverage score from the compact fields already available to SP. A candidate below the minimum coverage threshold can remain visible in ranking/advisory but cannot newly enter the executable Shadow target. Existing holdings are not forcibly sold solely because a field becomes unavailable; hard stop remains independent.

## Broader USA universe
Add an SP-specific broad US universe source by deduplicating S&P 500, S&P MidCap 400, S&P SmallCap 600 and Nasdaq-100 constituents. This produces roughly 1,500 unique large/mid/small-cap symbols when source pages are available. It uses cached public constituent lists with packaged fallback and does not widen the global app's ordinary USA scope.

## AI THINKS vs SHADOW EXECUTED
Persist and render two explicit sets: the current AI target/advisory and the actions actually executed in Shadow. Blocked actions retain their reason codes and gate reasons. UI must not imply that advisory SELL/BUY was executed.

## Safety and resource constraints
- No real orders.
- Hard stop bypasses ordinary rebalance gates.
- Deep analysis remains bounded; only broad coarse discovery expands.
- Existing 12h cache remains valid for non-executable display, while executable rebalance freshness rules remain stricter.
- All new behavior is TDD-covered.
