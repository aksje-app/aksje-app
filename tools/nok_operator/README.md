# NOK operator 2026.10.28.1

Run `START-HER.ps1` by copying its complete text into Windows PowerShell. It
installs this exact version and runs `1-KLARGJOR.cmd`'s prepare action. No ZIP
needs to be downloaded or transferred by hand.

Preparation ends at personal B with three unsigned `NOK_PRODUCTION_GRANT_V2`
requests, their `ACTIVATION_PREFLIGHT` receipts, actual stored settings, approved
cost rules, and one catalog fingerprint. It does **not** fetch quotes or claim a
live strategy run. Closed exchanges, delayed Yahoo quotes or zero execution-ready
candidates cannot stop an otherwise valid empty account from being activated.
Missing stored settings, invalid archives, changed history, missing actual input
provenance, nonempty accounts or invalid policy still stop readiness.

Only after reviewing the exact requests, run `2-GODKJENN-OG-AKTIVER.cmd` and type
`GODKJENNING B <the exact catalog fingerprint>`. It signs locally and calls the
existing `activate()` API. A wrong reference, changed settings, invalid signature,
changed source history or changed signed runtime preservation evidence fails
closed. The scheduler is never resumed. Activation creates no orders.

All quotes, FX conversions and held-position marks still use the unchanged
execution evidence validators (normally at most 15 minutes old). The new receipt
is explicitly NOT a `live_preview`; the genuine preview still requires actual
market evidence. Super Portfolio gets an in-memory authoritative market-policy
snapshot from `market_universe.py`; SHADOW/OFF scopes cannot be promoted, and a
stricter historical frozen policy stays stricter. No archived pipeline is edited.

## Existing private context

The package locates the original job and key-folder references automatically:
`%LOCALAPPDATA%\AksjeNokOperator\nok-job-20261024T165039Z`.
It uses the existing SSH key in `nok-job-20261024T162543Z`. Archive and operator
keys remain on the PC. Only the public certificates, original archive bytes,
verified decrypted archive bytes and grants travel through the authenticated
SSH stream. The only delegated crypto operation is decryption of the pinned
original CMS archive. Operator signing happens locally. No private key is copied
to Render, a delivery artifact, logs, PostgreSQL or GitHub.

The original archive and physical restore receipt are retained. Missing
verification files are rehydrated into private `/tmp` from the SAME sealed
archive and verified against EVERY original file hash. No database is restored
again and no restore receipt is invented. A wholly absent old runtime after
redeploy can be preserved explicitly via the verified archived files, only with
PostgreSQL canonical storage and fallback disabled. This absence is written into
the signed receipt. A present-but-changed runtime always fails. Production runtime
trees are never populated or rewritten by the operator. Full native database
fingerprints are checked again by the actual activation API.

## Interruptions

Ciphertext uploads use atomic promotion after complete SHA256 verification.
Partial bytes are preserved and appended only after matching the PC prefix hash.
SSH host checking remains strict, connect timeout is 20 seconds, keepalives detect
lost transport, OpenSSL operations have bounded timeouts, and a session has a
2-hour upper bound. The private SSH log and last received account receipts are
retained. There is no automatic activation retry following an unknown result.

After a disconnect, use the SAME reviewed B package with part 2. The existing
core activation is idempotent for the exact signed grant, including a connection
lost between authorization and route publication. A new Render `/tmp` is rebuilt
from the original PC archive and the exact locally signed requests; no replacement
account, grant or server-side signature is generated. Settings and all preservation
proofs are checked again. If their bindings changed, the operator stops for a new
review instead of changing what was approved. Activation is sequential across
three accounts, so a partial result can exist and is reported explicitly.

## Verification

`tests/test_activation_preflight_integration.py` exercises actual encrypted
archive/physical restore/native fingerprints, three existing DRAFTs, request/sign/
activate, closed and partially evidenced markets, immutable capitals/settings,
SQL routes, stale price/FX rejection, absent versus changed runtime, and exact-grant
recovery after a route-publication failure.

`tests/test_nok_operator_transport.py` executes the actual packaged worker in a
child process with a disposable PostgreSQL installation, original CMS archive and
PC-side crypto delegation. Only the SSH transport is replaced with a local pipe.
It runs prepare, personal-B binding/signing, connection loss after the first
activation receipt, loss of the remote working directory, and exact signed-package
completion with three SQL-confirmed active accounts and no forced trades. It also
checks interrupted upload resume and that remote files contain no private key.

These are isolated fixtures, NOT production activation receipts. Native Windows
and actual Render SSH still require the user's run after deployment and personal
B. No production activation, merge, deployment or scheduler change is performed
by running the test suite.
