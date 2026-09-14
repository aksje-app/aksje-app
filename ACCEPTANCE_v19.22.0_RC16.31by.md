# Acceptance - RC16.31by

RC16.31by is accepted only when all relevant live checks pass.

## A. Norway universe
- [ ] `source_authoritative_exchange_master = true`
- [ ] full official Norway universe remains active
- [ ] Oslo Børs / Euronext Growth Oslo / Euronext Expand Oslo counts are present
- [ ] candidate exchange metadata is present for `.OL` report candidates where the authoritative master contains it

## B. Market clock
- [ ] before 09:00 Norway closed status shows `Åpner 09:00`
- [ ] after close it shows the next ordinary weekday opening
- [ ] technical PDF column is `Neste ordinære åpning`

## C. Draft/report semantics
- [ ] night Utkast mission does not claim the job is a USA report
- [ ] technical report shows explicit analysis funnel stages
- [ ] report candidates and active deep-analysis population are clearly separated
- [ ] visible evidence status is `ready / evidence-controlled`
- [ ] legacy all-candidate evidence coverage is not presented as the main quality percentage

## D. Final export memory gate
- [ ] cleanup/reclaim runs before final export validation
- [ ] guard logs `pressure_basis=NON_RECLAIMABLE_PLUS_HARD_LIMIT`
- [ ] large `cgroup_file_mb` alone does not trigger a false stop
- [ ] genuine high non-reclaimable memory still blocks
- [ ] cgroup >=97% hard limit still blocks
- [ ] `final_artifact_sync.release_gate` becomes PASS/OK on a normal completed run

## E. BX workflow regressions
- [ ] Start Utkast reacts immediately and polls on PC and mobile
- [ ] no duplicate AUTONOMOUS candidate failure
- [ ] standard PDF, technical PDF, JSON and diagnostic ZIP are grouped together
- [ ] blocker text wraps fully
- [ ] web/scheduler/paper scanner use the same version and commit

## F. Scheduled runtime proof
- [ ] at least one normal 08:00 / 14:00 / 22:00 run completes without OOM/recovery failure
- [ ] report artifacts persist correctly
