# RC16.31bq – Manual Memory and Terminal Status Closure

Bygger på RC16.31bp.

## Endringer
- Autoritativ sluttstatus overskriver stale `progress_event=FAILED` når rapportkjeden faktisk er `COMPLETED/OK` og sluttporten er godkjent.
- Ny cgroup-diagnostikk deler `memory.current` i blant annet anon/file/kernel/slab slik at høy cgroup kan skilles fra høy Python-RSS.
- To-pass terminal minneopprydding med `gc`, `malloc_trim` og best-effort Linux cgroup v2 `memory.reclaim`. Reclaim er fail-safe dersom hosten gjør cgroup-filen skrivebeskyttet.
- Ny opprydding før siste COMPLETE-event og ny post-cleanup resource telemetry i bakgrunnsjobben.
- Scannertekst er policy-bevisst: når Norge-only er aktivt sier den ikke lenger «Alle markeder stengt» dersom USA/Brasil kan være åpne, men deaktivert av policy.

## Ikke endret
Ingen kjøpsgrense, risikogrense, likviditetsregel, Fresh Trend-logikk, porteføljeregel eller handelsmyndighet er endret.

## Live-akseptanse
Manual-report minne er ikke erklært ferdig lukket før Render viser post-cleanup cgroup med god margin. Mål: helst < 1.5 GiB, og aldri nær 2 GiB hard limit.
