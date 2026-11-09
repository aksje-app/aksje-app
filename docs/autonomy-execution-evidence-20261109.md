# Autonomy execution evidence handoff

The 9 November afternoon report MI-20261109-140750 recorded 60
`NO_EXECUTION` decisions with the same generic message. MORLD.OL and VEI.OL
passed analytical gates, but no trade was executed. The selected NOK Autonomy
account correctly retained 500,000 NOK cash and no positions. The source report
and cached preparation have the documented NOK currency under `raw`, not at
the top level. Their daily prices are not execution quotes.

The former exception handler discarded the provider exception. It is impossible
to reconstruct whether each historic failure was a price, currency, FX, or
other error. The fixes below address independently reproduced defects; they
are not proof that all 60 old failures shared one cause.

## Changes

- Read explicitly documented currency, raw execution quotes and FX from the
  same-ticker wrapper chain. Reject conflicting identities/currencies. Never
  infer instrument currency from a ticker suffix, or use a daily price as an
  executable quote.
- Keep live reference time current across the batch and after provider I/O.
  A new quote returned by a later/slower request must not be rejected against
  the clock captured before collection started. Explicit historical `at` calls
  retain deterministic validation.
- Revalidate price and FX age at the final collection time. The 15-minute
  limit is unchanged. Expired or future data remains blocked. Missing evidence
  for held instruments and Paper inputs still aborts rather than being skipped.
- Use the same collection code for live execution and read-only preview.
- Store specific, controlled reason codes for missing price, missing currency,
  missing FX, invalid cost policy, identity conflicts and expired/future data.
  Unknown provider exception text is not persisted because it may contain
  authenticated URLs. No financial journal, signature, fee, threshold, position
  sizing, opening balance or trade authorization is changed.

## Validation

Regression tests first failed against the original behavior for wrapper loss,
lost error reasons and a frozen batch clock. A separate reviewer reproduced an
additional intra-request clock defect; a six-minute provider-delay regression
now covers both fetching and post-fetch validation. Tests also cover provider
outage with cached documented evidence, nested FX, FX expiry, identity mismatch,
stale daily marks, no credential leakage, and Paper/held-position fail-closed.

The existing US subset preflight fixture now includes the documented USD/NOK
quote that real production evidence already requires. Five provider test doubles
accept the optional live clock argument without changing their behavior.

No historical signals are re-executed. Live acceptance requires the deployed
source, healthy services and evidence from a normal subsequent execution; a
missing/stale provider quote or a closed exchange remains a legitimate block.
