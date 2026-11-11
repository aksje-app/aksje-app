# Direct PDF viewing in Pushover

The user's required workflow is the native PDF viewer inside Pushover: Share -> Copy -> paste the PDF in ChatGPT. A file-picker workaround does not satisfy that workflow. Current Pushover report URLs return Streamlit HTML, and the transient static preview can disappear on deployment.

Serve validated durable PDF bytes directly at /reports/<token>.pdf with application/pdf, inline filename, GET/HEAD and single byte ranges. Reuse existing token/expiry/storage validation; missing/expired tokens404, storage failures503, never HTML or guessed files. No new storage or worker. Use the pinned Streamlit1.57 public st.App API for custom routes; web_runner keeps its heartbeat and launches the wrapper. No private server monkey patches.

Existing root report links redirect to direct PDF by default, so old Pushover messages also work. Explicit report_view=page preserves the current report page and native download fallback; with_report_return adds that option for in-app navigation. Same-origin token report URLs passed to Pushover are converted to the direct .pdf path centrally in notifier, including quality/learning reports; unrelated URLs remain untouched.

Approaches: transient static PDF links recreate the old opening behavior but fail after restarts; adding more download controls leaves the required clipboard flow unresolved; direct durable HTTP PDF delivery is selected because it restores the native viewer while retaining expiry and fallback. This is an implementation choice under the user's explicit restoration request, not an assertion that physical iPhone clipboard behavior has been tested.

Validate HTTP contracts and unchanged bytes, malformed/expired/error cases, ranges/HEAD, unrelated routes, fallback page opt-in and actual server cold restart. One independent review and one CI, then already-authorized merge/deploy. Verify the existing real PDF in production without sending another notification or running analysis/trades. Final Pushover Share/Copy/paste must still be confirmed on the user's phone.
