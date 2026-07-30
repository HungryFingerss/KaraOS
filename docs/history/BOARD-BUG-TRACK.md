## Board-bug remediation track — original 10-bug scope (CLOSED 2026-05-21 at P0.B5 closure)

The 10 bugs surfaced by the skeptic1 / skeptic2 / ceo-evening board meetings 2026-05-20/21 mapped to the P0.B remediation track. P0.B5 closes the LAST 4. Original 10-bug board-meeting scope 100% addressed at spec level.

| # | Name | Spec | Status | Closure date |
|---|---|---|---|---|
| 1 | FAISS async rebuild missed DB UPDATE (Finding 1) | [P0.B2](complete-plan.md#p0b2--faiss-async-rebuild-correctness-bug-1--bug-2-missing-db-update-on-async-path--documentation-drift-d1d2d3d4d5--10-anchors--ordering-invariant-comment-block--sentinel-discipline--closed-2026-05-21) | CLOSED | 2026-05-21 |
| 2 | Documentation-vs-reality drift at `test_faiss_atomicity_invariants.py:29-32` | [P0.B2](complete-plan.md#p0b2--faiss-async-rebuild-correctness-bug-1--bug-2-missing-db-update-on-async-path--documentation-drift-d1d2d3d4d5--10-anchors--ordering-invariant-comment-block--sentinel-discipline--closed-2026-05-21) | CLOSED | 2026-05-21 |
| 3 | Kuzu schema upgrade SQL-commit ordering (Finding 2) | [P0.B3](complete-plan.md#p0b3--kuzu-schema-migration-ordering--kuzu-health-observable-finding-2--vulnerability-b-d1d2--7-anchors--ordering-invariant-comment-block--grep-baseline-before-drafting-doctrine-elevation-closed-2026-05-21) | CLOSED | 2026-05-21 |
| 4 | VoiceEvidence not frozen (BUG-SS-1) | [P0.B1](complete-plan.md#p0b1--reconciler-hygiene-bug-4-voiceevidence-not-frozen-d1--7-anchors--twin-filename-doctrine-extension--closed-2026-05-21) | CLOSED | 2026-05-21 |
| 5 | Reconciler `_p4_single_segment_mismatch` "dead" (BUG-REC-1) | P0.B1.X | **WONTFIX** (adjudicated 2026-05-21 by Jagan post-P0.B6 closure) — current cascade behavior is intentional design; phantom-stranger concern acknowledged-with-rationale (bootstrap-credit gates + dream-loop pruning handle phantom cleanup via natural expiry; cost of phantom-stranger creation is bounded transient session vs cost of wrong-attribution-to-holder unbounded memory pollution). Cascade comment at `core/reconciler.py:560-567` preserves the 2026-04-28 Lexi-misattribution regression warning. | 2026-05-21 (WONTFIX) |
| 6 | Together.ai SPOF across knowledge pipeline (Attack 6) | P0.B4 | SKIPPED per Jagan 2026-05-21 (deferred to user-defined trigger; architect-flagged design dialogue required) | — |
| 7 | BUG-EL-1 — test isolation `_safe_emit_failure_count` not reset | P0.B5 | CLOSED | 2026-05-21 |
| 8 | BUG-EL-2 — `stop_writer()` hangs on writer-task death | P0.B5 | CLOSED | 2026-05-21 |
| 9 | Finding 3 — `_save_faiss()` RLock re-entrancy implicit | P0.B5 | CLOSED | 2026-05-21 |
| 10 | V5 — `state.json` GIL-dependent race | P0.B5 | CLOSED | 2026-05-21 |

Cross-referenced from the Architectural Disciplines section (each closed spec's track-record bumps are honored at the doctrine sites). Future board-meeting bug enumerations get a new section below this one.

---
