> **CHAPTER 16 — P0 Correctness Foundations + Store/Session Migrations** | Sourced from `everything_about_system.md` §233-270 (verbatim mechanical extraction per Plan v2 §1.6 section-number stability invariant).

---

## 233. Why a Correctness Cycle Came First

The P0 work that landed in early May 2026 (P0.1 – P0.5, P0.13) targeted a different layer of the system than the bigger architectural sub-PRs that followed. These were correctness regressions surfaced by live canaries, not architectural debt. Each one was a small fix — usually 5–30 lines of production change — paired with a structural invariant test that prevents the regression class returning silently.

The grouping is deliberate: each P0.* item below is a separate failure mode with a separate AST-level guard, but they share an underlying methodology. **Fix the production code in one commit; ship the structural invariant in the same commit; cap the invariant at zero in a CI-enforced test; let the invariant catch any future drift.**

This is the methodology that escalated into the structured-audit-vs-reactive-patching lesson at P0.4 (§329). The earlier P0.1 – P0.3 items shipped reactive-patching style, then P0.4 (§238) demonstrated that *systematic* audit surfaces ~3–5× more sites than reactive patching catches. The retroactive read on P0.1 – P0.3 is that they were each the tip of a class — and the class itself was caught by the audit.

## 234. P0.1 — No Raw `"disputed"` Comparisons Outside the Helper

`_is_disputed()` (Part XV) was the canonical predicate for checking whether a session's `person_type` is in disputed state. It centralises the comparison so the dispute state machine can evolve without scattering string literals throughout the codebase.

The drift: live canary log lines started showing `person_type == "disputed"` checks at scattered call sites in `pipeline.py` and `core/brain_agent.py`. Each one was a tiny copy-paste of the helper's body. None individually was wrong. Collectively, they made the helper non-canonical — any future change to dispute state representation (e.g. moving from string to enum) would silently miss these sites.

**Fix:** every raw `== "disputed"` outside `_is_disputed()` was rewritten to call the helper. **Invariant:** `tests/test_no_raw_disputed_comparisons.py` (P0.1) AST-scans `pipeline.py` (excluding `_is_disputed()`'s own body) and every `core/*.py` (excluding `core/config.py` for type annotations) for `Compare` nodes where the right-hand side is the literal string `"disputed"`. The test fails if any site is added outside the helper.

One allowlist: `core/brain_agent.py:2216` uses an inline `# disputed-row-status` marker for a knowledge-row status column check that can't route through the helper due to a circular import. The allowlist marker is the explicit single exception; the AST scanner reads it as "this is a known site, do not flag".

## 235. P0.2 — `prior_person_type` Fail-Closed Default

The dispute state machine captures `prior_person_type` on every dispute-trigger event (§102) so that auto-clear (§51) can restore the speaker's role correctly after the dispute resolves. If the field is missing — for example because a future code path added a new dispute-trigger site without remembering to write the field — the default should be the lowest privilege.

The drift: two scattered sites in `pipeline.py` defaulted the missing field to `"known"` rather than `"stranger"`. A best_friend session whose `prior_person_type` was never written would silently auto-clear back to `"known"` — a privilege downgrade. Worse, in the reverse direction, a stranger session whose `prior_person_type` was never written and then somehow flipped to disputed would auto-clear *up* to `"known"` — a privilege escalation.

**Fix:** both sites now default to `"stranger"` (fail-closed). Even a missing field cannot grant privileges the speaker didn't have. **Invariant:** `tests/test_prior_person_type_default.py` (P0.2) — 20 AST structural tests covering 9 violation shapes and 10 legitimate patterns. The shape `_sess.get("prior_person_type") or "known"` is forbidden; `or "stranger"` is required.

The naming "fail-closed" carries explicit semantics: when a security-relevant default has to be picked, pick the one that grants the *least* privilege, so that the missing case can never silently grant more access than the writer of the field would have intended.

## 236. P0.3 — Multi-Word Name Contiguous Substring Fix

The `_user_text_gate_passes` primitive (§115) verifies that an LLM-proposed mutation tool argument (e.g. the proposed new name in `update_person_name`) was actually said by the user, by checking it appears as a substring of the most recent user_text. This is the architectural seam that prevents LLM hallucination from renaming people who never asked to be renamed.

The pre-fix v1 implementation used a `(\w+)` capture group to grab the first word of the proposed name, then a `_remainder` check (`_remainder in user_text`) to verify additional words also appeared. The bug: `_remainder` could appear *anywhere* in the user_text. A user saying "call me Sarah and my friend is Jane" would let the LLM hallucinate a rename to "Sarah Jane" — because "Sarah" and "Jane" both appear in user_text, just not contiguously.

**Fix (v3):** replaced the buggy remainder block with a single contiguous-substring check `if _nv_lower in _lt`. The full proposed name must appear as a contiguous substring of user_text. Also applied `_nfkc_lower()` (NFKC normalization + casefold) to all three inputs (user_text, new_value, captured) for homoglyph defense. **Tests:** `tests/test_user_text_gate_multiword.py` covers 25 behaviour cases (single-word baseline / legitimate multi-word contiguous / non-contiguous discriminating cases that v1 allowed and v3 rejects / fabrication-rejection / empty / None) and `tests/test_user_text_gate_invariants.py` covers 5 structural + behavioural invariants.

## 237. P0.13 — The Repeat-Guard Invariant Test

Session 70's Bug Q (Part XVI §113) introduced the **tool repeat guard** — when the LLM emits the same `(tool_name, args)` two turns in a row, the second call is suppressed. The mechanism is a per-session set of `_repeat_guard_key` and `_repeat_guard_count` fields, cleared by `_close_session` (Part VIII §50).

The drift surface: any new code path that proactively spawns a fresh tool call without going through the normal `conversation_turn` flow could accidentally bypass the repeat guard by writing to the session dict directly. P0.13 is the AST structural invariant that prevents this.

`tests/test_repeat_guard_invariant.py` walks the parent-annotated AST of `pipeline.py` (via the new zero-import `core/pipeline_invariants.py` module that exposes `REPEAT_GUARD_FIELDS` and `ALLOWED_REPEAT_GUARD_FUNCS`). Five violation detectors fire on any direct mutation of repeat-guard fields outside the allowlisted helpers: `pop`, `del`, `assign None`, `update`, `clear`. The allowlisted functions are the legitimate writers (`_execute_tool`, `_close_session`, plus a small set of dispute-clear paths) — any direct mutation outside the allowlist fails the test.

The test uses *full parent-walk analysis* (`_is_inside_allowlisted_function` walks every ancestor) which is important: a later refactor that decomposes `_execute_tool` into nested helpers must continue to be exempt, because the nested helpers are conceptually still inside the allowlisted function. The refactor doesn't have to update the test.

---

# Part XXXVII — The Silent-Except Audit (P0.4)

## 238. The Reactive-Patching Anti-Pattern

Before P0.4, the standard response to a `except Exception: pass` discovered during a debugging session was to fix the one site and move on. A few months of this had surfaced ~7 silent-except sites, fixed one at a time, with no systematic audit.

The reactive-patching mindset assumes that catching the bugs *as they bite* is sufficient. In practice — empirically demonstrated by P0.4 — reactive patching catches roughly 30% of the class. The other 70% sits in production code, swallowing failures that nobody has needed to debug yet.

The realisation: an AST-based project-wide scan would surface every silent-except in one pass. The scan would also become the structural invariant that prevents the class returning. The combined cost — audit + invariant + remediation — is small (about 3-5 hours total). The combined value — every silent failure mode either fixed or explicitly justified — is enormous because of the next-bug-debug-time saved.

## 239. AST Detector Anatomy

`tests/test_silent_except_invariant.py` ships before any production-side fix. Three helpers compose the detector:

- **`_is_broad_except_handler(node)`** — returns True iff the `ast.ExceptHandler`'s `type` is one of: `None` (bare `except:`), an `ast.Name` matching `Exception` or `BaseException`, or an `ast.Tuple` whose elements include `Exception` or `BaseException`.
- **`_is_silent_pass_only_body(node)`** — returns True iff the handler's body is exactly `[ast.Pass]`. A body with logging, re-raise, return, or any other statement does not match. The discipline is *silent* pass-only; logged pass is fine.
- **`_has_annotation_comment(node, source_lines)`** — looks for `# RACE:`, `# CLEANUP:`, `# OPTIONAL:` on the `pass` line, the `except` line, or the line directly above. The 3-line co-location window captures both common styles (annotation above the except header, or inline with the pass).

Allowlist with boundary-correct check: `rel_str == allow or rel_str.startswith(allow + "/")`. This prevents `core/_minifasnet_helper.py` from matching `core/_minifasnet` allowlist entry through accidental string prefix collision.

Injectable `rel_str` param on `_scan_file` so detector self-tests exercise the real code path with synthetic input. The self-tests live in the same test file and demonstrate that the scanner rejects unannotated handlers and accepts each of the three permitted annotations.

## 240. The 22 Surfaced Sites and the Three Permitted Annotations

Running the audit found **22 sites** across 9 production files: `core/audio.py`, `core/brain.py`, `core/brain_agent.py` (6 sites), `core/classifier_graph.py`, `core/db.py` (2), `core/state.py`, `core/vision.py`, `pipeline.py` (8), `sim_runner.py`. Compared to the ~7 sites that had been caught reactively across the prior few months, that's a discovery ratio of roughly 3×.

The three permitted annotations encode genuinely different rationales:

- **`# RACE:`** — the handler swallows a known race condition (e.g. a concurrent close racing with a write). Re-raising would cascade a benign-but-unavoidable race into a visible failure. The annotation must be followed by a brief description of what races and why suppression is correct.
- **`# CLEANUP:`** — the handler is in a cleanup or finalisation path where the only error mode is the cleanup operation itself failing. Re-raising would mask the original error that triggered cleanup.
- **`# OPTIONAL:`** — the handler is in a best-effort observability or instrumentation path where the production behaviour is intentionally unaffected by the failure. `safe_emit_sync` (Part XLIX §314) is the canonical example: event-log emission is best-effort, a producer-hook bug must never break the production path.

Any site not matching one of these three rationales must be fixed (re-raise, log + re-raise, or replace with a typed handler).

## 241. Bulk Annotator and the One-Shot Closure

The remediation tool `tools/bulk_annotate_p04.py` is idempotent: a single pass adds `# TODO-P0.4: triage` to the pass line of every unannotated site. The annotation is a *temporary* permission — `# TODO-P0.4:` was originally in `PERMITTED_ANNOTATIONS` so the invariant test went green on the first run, then each site was triaged in 7 batches (B1 – B7) and the temporary marker was either replaced with one of the three real annotations or removed alongside a real fix.

P0.4 Batch 7 closed the cycle: `# TODO-P0.4:` was *removed* from `PERMITTED_ANNOTATIONS`. From that commit forward, the marker is itself a violation — meaning the structural invariant no longer accepts the "to be triaged later" escape hatch.

The empirical lesson banked in §329: **22 sites surfaced via AST audit; ~7 had been caught reactively; the gap (~70%) is what motivates the structured-audit-vs-reactive-patching discipline.** Subsequent P0 items (P0.5 inverse check, P1.A1-slice layering audit at 9 sites vs 2 known reactively, a 4.5× discovery ratio) confirmed the ratio.

---

# Part XXXVIII — Cross-Storage Atomicity (P0.5 + P0.X)

## 242. The Paired-Write Failure Class

Kara-OS's persistence layer is *not* a single SQL database. It's three durable stores that have to stay consistent: SQLite (`faces.db` + `brain.db`), FAISS (the face index), and Kuzu (the knowledge graph). Every write that touches more than one of these stores is a **paired write**, and every paired write has a failure mode: the first half commits, the process crashes before the second half, and the next boot sees divergent state.

The pre-P0.5 architecture had paired writes scattered through `core/db.py` and `core/brain_agent.py` with no consistent ordering, no atomicity guarantee, and no boot reconciliation. The empirical bug fingerprint: `add_embedding` updated FAISS *before* committing the SQL row. A SQL INSERT failure (e.g. UNIQUE constraint violation, disk full, race with `delete_person`) left an orphan in FAISS with no corresponding DB row. `_load_faiss()` on next boot saw `ntotal > COUNT(*)` but had no mechanism to detect or repair the divergence.

P0.5 (FAISS ↔ faces.db) and P0.X (Kuzu ↔ brain.db) ship the architectural pattern that closes this failure class across both pairs.

## 243. P0.5 — FAISS ↔ faces.db SQL-First Ordering

The pattern applied to all 5 paired-write methods of `FaceDB` (`add_embedding`, `delete_person`, `prune_old_strangers`, `prune_zero_value_stranger`, `prune_outlier_embeddings`):

```python
with self._index_lock:
    with self.transaction():           # 1. SQL durable
        # SQL ops only — NO FAISS calls inside the transaction
    try:                               # 2. FAISS derived state
        self.index.add(...) / self._rebuild_faiss()
        self._save_faiss()
    except Exception:
        self._mark_faiss_dirty()       # sentinel → boot reconciliation
        raise
```

The contract: **SQL is the authoritative store; FAISS is derived state that can always be rebuilt from SQL.** SQL writes commit first inside a transaction. FAISS writes happen after the SQL commit. If FAISS writes fail, a sentinel file is touched on disk and the exception is re-raised. Boot reconciliation reads the sentinel and rebuilds FAISS from SQL.

`FaceDB.transaction()` is a context manager that issues `BEGIN IMMEDIATE` (with the S65 rollback race tightened — see §282) so concurrent connections can't interleave their writes.

## 244. Sentinel Files and Boot Reconciliation

Three sentinel helpers on `FaceDB`:

- **`_sentinel_path()`** — returns the path to the `_faiss_dirty.sentinel` file alongside the FAISS index file.
- **`_mark_faiss_dirty()`** — touches the sentinel file. Used in the `except` branch of every paired-write method.
- **`_clear_faiss_dirty()`** — deletes the sentinel file. Used after `_rebuild_faiss()` completes successfully at boot.

`_load_faiss()` at startup checks the sentinel OR computes a count-mismatch (FAISS `ntotal` vs SQL `SELECT COUNT(*) FROM embeddings`). If either is non-empty, `_rebuild_faiss()` is called, the sentinel is cleared on success, and the system continues. If rebuild fails at boot, `_faiss_degraded = True` is set on the FaceDB instance, the sentinel is preserved (so the next boot tries again), and `recognize()` returns `(None, None, 0.0)` for the rest of the session. The system degrades to no-face-match rather than crashing.

The bug fingerprint preserved as a regression test in `tests/test_faiss_sql_atomicity.py`: Test 1 asserts `db.index.ntotal == pre_faiss_size` after a forced SQL crash. Pre-fix FAISS-first ordering leaves `ntotal=1` (orphan). Post-fix SQL-first ordering leaves `ntotal=0` (SQL rolled back, FAISS never touched). The test passes only against the post-fix code.

## 245. The Inverse-Check Discipline

`PAIRED_WRITE_METHODS = ("add_embedding", "delete_person", "prune_old_strangers", "prune_zero_value_stranger", "prune_outlier_embeddings")` — a hand-curated tuple in `tests/test_faiss_atomicity_invariants.py`. **Forward check:** every method in the tuple is verified to follow the SQL-first + sentinel + `_index_lock` pattern via AST scan.

That was the obvious half. **Inverse check:** every method on `FaceDB` that calls into FAISS (regex pattern matching `self.index.add` / `self._rebuild_faiss` / `self._save_faiss`) is asserted to be a member of `PAIRED_WRITE_METHODS`. The two halves together close the loop: any future method added without registration silently fails the inverse check.

The empirical lesson — and the reason inverse checks became standard practice — is that the inverse check on P0.5 **caught a real bug in the same session**. `prune_outlier_embeddings` was a hidden paired-write site: it called `_rebuild_faiss()` directly without `_index_lock`, without `transaction()`, and without `_mark_faiss_dirty()`. The forward check would have happily passed an empty tuple. The inverse check failed loudly and forced the fix.

The closure-time effort to add the inverse check was about 30 minutes. It caught a 7th bug from one P0 cycle. The discipline is now applied to every enumerated method tuple in the codebase: PAIRED_WRITE_METHODS in P0.5, VOICE_GALLERY_METHODS, the Kuzu Three-Pattern detectors in §246, the EXPECTED_RULES_BY_BAND map in §291, the `_TOOL_HANDLERS` dispatch table in §272, the producer-hook coverage in P0.0.7 (Part XLIX).

## 246. P0.X — The Three Kuzu Write Patterns

Kuzu (the knowledge graph) is a separate store from brain.db (the SQL knowledge table). They have to stay consistent: every fact extracted by `ExtractionAgent` lands in *both* (brain.db row + Kuzu nodes/edges). The pre-P0.X architecture had cross-write code scattered across `BrainOrchestrator._process_turn`, `_retroactive_scan`, `on_identity_confirmed`, and `_persist_extraction_to_kuzu` — with no consistent pattern for what happens when one half fails.

P0.X codified three patterns and enforced each with an AST detector:

| Pattern | What it does | Where it's used |
|---|---|---|
| **`SCHEMA_MIGRATION`** | Always rebuilds Kuzu from brain.db. Inherently safe because brain.db is authoritative. | `_ensure_graph_sync()` at boot |
| **`RAISE`** | SQL transaction first, sentinel touched before Kuzu op, sentinel cleared on Kuzu success, re-raise on Kuzu failure | `on_identity_confirmed` — the user-visible rename path; the user gets an explicit failure, not silent divergence |
| **`SWALLOW`** | Kuzu try/except with sentinel touched + log, no re-raise | `_persist_extraction_to_kuzu`, `_retroactive_scan`, `_process_turn` — brain.db is authoritative, Kuzu heals on next `_ensure_graph_sync()` |

The pattern choice is per call site, decided by the question: **does the user need to know if Kuzu writes fail right now?** If yes (rename), use RAISE. If no (background extraction), use SWALLOW. SCHEMA_MIGRATION is the bootstrap-reconciliation path that picks up after either.

## 247. SCHEMA_MIGRATION, RAISE, and SWALLOW in Detail

Sentinel machinery on `BrainDB`:

- `_kuzu_dirty_path()` — sentinel file path.
- `_mark_kuzu_dirty()` — touches the sentinel before any Kuzu write.
- `_clear_kuzu_dirty()` — clears the sentinel after a successful Kuzu write.
- `_is_kuzu_dirty()` — reads the sentinel at boot.

Boot reconciliation in `BrainDB.__init__`: if `_is_kuzu_dirty()` is True, force `_ensure_graph_sync()` to rebuild on next access; `_kuzu_degraded: bool` flag is set if rebuild fails. Degraded mode causes graph reads to return empty rather than crash.

AST detector self-tests live in `tests/test_kuzu_atomicity_invariants.py` and prove that each helper catches exactly the violations it claims. The RAISE-pattern detector rewrites raise-detection to walk `ast.Try` nodes and find specifically the Kuzu-writing try block (by scanning the try body for Kuzu write markers) before inspecting its except handlers for `ast.Raise`. The pre-fix detector would find any `raise` in any except handler, including the SQL transaction wrapper's, and report false passes.

## 248. `_process_turn` — The Hidden Paired-Write Site

Inverse check at work again: `_process_turn` in `BrainOrchestrator` had `self._graph_db.invalidate_fact(...)` inside the ContradictionAgent loop **without** `_mark_kuzu_dirty()`. The inverse check (`test_all_kuzu_write_sites_are_covered`) found it. Two forward tests were added at closure: sentinel-written + no-re-raise for `_process_turn`.

Same shape, same lesson: registering enumerated tuples without inverse checks lets new call sites slip in undetected. The inverse check is the cheap insurance.

## 249. Degraded-Mode Fallback Behavior

`_faiss_degraded = True` → `FaceDB.recognize()` returns `(None, None, 0.0)`. Face-recognition flow continues to background-scan and pyannote-route on voice signals; the system functions without face match (degraded from "best-friend recognised on camera" to "voice-only attribution"). The dashboard receives a `state.json` update reflecting the degraded condition.

`_kuzu_degraded = True` → graph reads return empty. `find_shared_entities`, `_apply_household_extraction`, and similar paths see no graph data; the LLM prompt loses the graph context but continues to receive brain.db facts. Recovery happens on the next `_ensure_graph_sync()` cycle if the underlying issue (file lock, disk space) resolves.

The degraded modes are not silent. Each one logs a `[FAISS]`/`[Kuzu]` `WARN: degraded mode active` line. The health log (Part XLVI §301) doesn't surface them yet — adding `faiss_degraded` and `kuzu_degraded` fields to `HealthSnapshot` is a small follow-up worth doing alongside the Wave-5 fields.

---

# Part XXXIX — The Store-Pattern Migration (P0.6)

## 250. Why 28 Module-Level Globals Was a Problem

By early 2026 `pipeline.py` had accumulated 28 module-level mutable globals: `_persons_in_frame`, `_unrecognized_tracks`, `_stranger_track_map`, `_track_identity`, `_conversation`, `_last_greeted`, `_voice_gallery`, `_voice_gallery_sizes`, `_emotion_agents`, `_sessions_started`, `_active_room_session`, `_cloud_state`, `_cloud_failed_at`, `_pipeline_state`, `_active_system_name`, `_detected_lang`, `_latest_vision_frame`, `_latest_frame_time`, and many more.

The cost showed up in three places:

1. **Test isolation.** Each global needed an explicit reset in test fixtures. Many tests forgot. Failures cascaded: a test that set `_persons_in_frame` left state for the next test, which silently passed off the residual state and then failed unpredictably when run in a different order.
2. **Concurrent access.** Some globals were mutated from background coroutines (vision loop, KAIROS, dream loop). The mutation patterns were ad-hoc — sometimes a lock, sometimes not, sometimes a `.copy()`, sometimes a direct reference. The mutations interleaved during full-suite test runs and produced sporadic failures.
3. **Coupling.** A code change in one part of pipeline.py would silently affect another part through the shared globals. Vision tests would pass but voice tests would fail in unrelated ways because the order of writes to `_persons_in_frame` had changed (Part XXXII §198 documents this in the voice/vision context).

P0.6 ships the **Store pattern**: each cluster of globals is encapsulated in a typed class with async mutators, sync peek reads, and an explicit `reset()` method called by an autouse pytest fixture.

## 251. The `Store(ABC, Generic[T])` Base Class

`core/store_base.py`:

```python
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")

class Store(ABC, Generic[T]):
    """Base class for all P0.6 pipeline-state stores.

    Subclasses must:
      - Define async mutator methods (require asyncio.Lock if mutating shared state).
      - Define sync peek_* methods for read-only access (no lock acquisition).
      - Implement reset() to restore the canonical empty / initial state.
    """

    @abstractmethod
    def reset(self) -> None: ...
```

Every store inherits from `Store`. The `reset()` method is the autouse-fixture-callable hook that makes test isolation deterministic.

## 252. The Eight Stores and What Each Owns

| Store | Module | Owns |
|---|---|---|
| `PresenceStore` | `core/presence_store.py` | `_persons_in_frame` (which person_ids are visible on camera + face_match_conf + source tag) |
| `TrackStore` | `core/track_store.py` | `_unrecognized_tracks`, `_stranger_track_map`, `_track_identity`, `_unrecognized_embeddings` |
| `ConversationStore` | `core/conversation_store.py` | `_conversation` (per-pid message history), `_last_greeted`, `_last_self_update`, `_compact_pids` |
| `VoiceGalleryStore` | `core/voice_gallery_store.py` | `_voice_gallery` (in-memory mean embeddings), `_voice_gallery_sizes` (DB-backed cache) |
| `PerPersonAgentStore` | `core/per_person_agent_store.py` | `_emotion_agents` (per-pid EmotionAgent instances), `_sessions_started`, `_ambient_wake_pending` |
| `CacheStore` (×4 instances) | `core/cache_store.py` | `_compact_history_cache`, `_query_embedding_cache`, `_intent_classifier_cache`, `_bf_id_cache` |
| `PipelineStateStore` | `core/pipeline_state_store.py` | `_cloud_state`, `_pipeline_state`, `_active_room_session`, `_active_system_name`, `_detected_lang`, `_last_face_seen`, `_last_user_speech_at`, `_last_kairos_at`, `_last_silent_update`, plus the cloud transition methods |
| `VisionFrameStore` | `core/vision_frame_store.py` | `_latest_vision_frame`, `_latest_frame_time`, `_vision_prev_det_count` |

Each store has between 5 and 25 methods. The total LOC for the eight modules is ~3500 lines, but the migration *removed* roughly the same amount from `pipeline.py` — net architectural improvement, not net code growth.

## 253. Async Mutators, Sync `peek_*` Reads, and the Single-Owner Invariant

The convention across all eight stores:

- **Async mutators** (`async def set_x(...)`, `async def append_y(...)`, etc.) acquire the store's `asyncio.Lock` before mutating. The lock guards against concurrent writes from multiple coroutines.
- **Sync `peek_*` reads** (`def peek_x(...)`) do *not* acquire the lock. They read the canonical structure once and return either a copy (for mutable collections like lists/dicts) or the value directly (for immutable types like strings/ints). The contract is: peek reads are cheap, called from synchronous contexts (logging, prompt assembly), and must never block.
- **Single-owner invariant**: each store is instantiated exactly once at module level. No code outside the store module mutates the underlying data; everything goes through the store API.

`tests/test_p06_store_invariants.py` enforces these conventions via AST scan. `_STORE_MODULES` enumerates the eight modules; each one is asserted to inherit from `Store`, to expose only async-marked mutators (with a small allowlist for legitimately-sync mutators like `__init__`), to have a `reset()` method, and to be the sole writer of its owned fields (cross-checked against grep of the module-level names).

## 254. The Producer-Copy Invariant

`VisionFrameStore.set_frame(frame, frame_time)` accepts a numpy ndarray. The frame is a *shared* reference produced by the camera capture loop. If the store kept the reference and another consumer mutated the frame in place, every reader would observe the mutation. Worse, the SORT tracker (Part IV §21) mutates its input arrays as part of its bounding-box update.

**The rule:** producers MUST call `.copy()` on the frame before passing it to `set_frame`. The store doesn't copy internally — it would be wasteful in cases where the producer already has a copy.

The structural invariant: `tests/test_vision_frame_store_producer_copy.py` AST-scans `pipeline.py` for every `set_frame(...)` call site and asserts `.copy()` appears in the same expression (either on the frame argument directly, or on a binding visible in the same scope). One of the eight P0.6.7v2 deliberate-regression checks (§258) injected a frame passed without `.copy()` and confirmed the test fires.

## 255. Peek-Not-Mutate Semantics for CacheStore

The original `CacheStore` had a touch-on-read LRU: every `get(key)` not only returned the value but also moved the key to the end of the OrderedDict (most-recently-used). This violated the spec's locked decision (cache should be `peek`, not `touch`).

The drift was caught in the v2 closure audit (Part L §322 — induction-surfaces-invariant-gaps). v2 renamed `get()` → `peek()`, removed `move_to_end` touch-on-read, replaced OrderedDict with a plain dict, and eviction on `set()` now picks the oldest-by-cached-at via `min(_data, key=lambda k: _data[k][1])`. `_hits` and `_misses` are documented as read-side observability counters with `# OBSERVABILITY:` annotation — they're written from `peek()` for counting purposes but they do *not* affect cache behavior.

The deliberate-regression check that proved the fix: inject `touch-on-read` promotion logic into `peek()` and confirm a behavioral test (cache should evict oldest under bounded capacity even when oldest is read recently) fails with the injection and passes with the spec'd peek-not-mutate.

## 256. The Prior-State Guard for Cloud Transitions

`PipelineStateStore.transition_to_online()` was originally idempotent (could be called multiple times with no side effects). The v1 implementation set `cloud_recovered = True` on every call. The drift: a retry path that called `transition_to_online()` twice in quick succession spuriously fired the `cloud_recovered` flag, causing the recovery flow (Part XII §79) to emit a leaky "cloud connection just came back online" TTS narration on every retry rather than only on the actual SICK→ONLINE transition.

v2 fix: gain a prior-state check. `cloud_recovered = True` is set *only* if the prior state was NOT already ONLINE. Idempotent retry no longer spuriously signals recovery. One of the eight deliberate-regression checks (§258) injected the guard removal and confirmed the recovery TTS was spuriously emitted.

## 257. Autouse-Fixture Reset and the M2 Coverage Meta-Test

`conftest.py` (root) and `tests/conftest.py` both contain an autouse fixture `_reset_pipeline_state_between_tests` that calls `reset()` on every Store. The fixture is autouse, so every test runs against a clean state by default.

The M2 coverage meta-test (`test_p06_store_invariants.py::test_autouse_fixture_resets_all_stores`) AST-scans both conftest files and asserts every store name is in the reset loop. The 9th store added (SessionStore — added by P0.7) was caught by M2 the first time the test ran with only 8 entries in the reset list — the meta-test forced the conftest update before P0.7 could land.

## 258. The Eight Deliberate-Regression Checks at v2 Closure

After v1 shipped and the closure audit caught three gaps (vision globals missed, CacheStore touch-on-read, prior-state guard), v2 incorporated all three plus the architectural invariants from §253–§256. Closure for v2 ran eight deliberate-regression checks, one per invariant, and all eight fired correctly:

| # | What was injected | Test that fired | Reverted? |
|---|---|---|---|
| 1 | Added a new field to `PresenceStore.EXPECTED_FIELDS` schema | `test_presence_store_schema` (field-set drift) | Yes |
| 2 | Added a writer to `_persons_in_frame` outside `PresenceStore` | `test_no_external_writes_to_presence_store` | Yes |
| 3 | Stripped paired-write atomicity from `transition_to_sick` | `test_cloud_bundle_paired_write_atomic` | Yes |
| 4 | Passed a frame to `set_frame` without `.copy()` | `test_vision_frame_store_producer_copy` | Yes |
| 5 | Injected `move_to_end` touch-on-read into `CacheStore.peek` | behavioral cache eviction test | Yes |
| 6 | Re-added a legacy global at module scope in `pipeline.py` | `test_p06_legacy_global_progress` (ratchet at cap=0) | Yes |
| 7 | Dropped a store from the conftest reset loop | M2 autouse meta-test | Yes |
| 8 | Removed the prior-state guard from `transition_to_online` | behavioral cloud-recovery TTS test | Yes |

The pattern is the induction-surfaces-invariant-gaps discipline (Part L §322) at work: each invariant gets tested by injecting its own violation, confirming the test fires, then reverting. v2 closure went green only after all eight checks confirmed correct behaviour.

## 259. The Legacy-Global Ratchet at Cap = 0

`tests/test_p06_legacy_global_progress.py` is the migration-progress ratchet. It AST-scans `pipeline.py` for module-level assignments to a fixed enumeration of 28 legacy global names (`_persons_in_frame = ...`, `_voice_gallery_sizes = ...`, etc.) and asserts the count is below a configurable cap. During the migration the cap stepped down (28 → 25 → 20 → ... → 0). At closure the cap is 0: any reintroduction of a legacy global fails CI.

The detector uses word-boundary discipline. Initially it caught false positives like `initial_cloud_state=...` (kwarg, not a global write) — the regex was tightened to require word-boundary delimiters on both sides of the global name.

The inverse check enumeration was also updated for the legitimate writers: `__init__` is allowed to conditionally assign `_cloud_state` and `_pipeline_state` after `reset()`. The allowlist captures the constructive paths, the ratchet blocks the destructive paths.

## 260. The Schema and Inverse-Check Ratchets That Lock It In

Four invariant tests, run every PR, lock the migration as a permanent structural property:

1. **Ratchet** — `test_p06_legacy_global_progress.py` at cap=0 (above).
2. **Schema pinning** — `test_p06_store_schemas.py` pins `EXPECTED_FIELDS` per Store across 15 schema tests. Drift in any owned-field set fails CI.
3. **Inverse checks** — `test_p06_store_inverse_checks.py` enforces paired-write discipline via 19 AST-based inverse checks: cloud-bundle (4-field atomic), room-triple-tuple (3-field atomic), VoiceGalleryStore (gallery, sizes) pair, VisionFrameStore (frame, frame_time) pair, plus per-field writer enumeration for the simpler stores.
4. **M2 autouse meta-test** — verifies both conftest files reset all 9 stores (8 P0.6 stores + 1 P0.7 SessionStore).

Plus the producer-copy AST source-inspection test (`test_vision_frame_store_producer_copy.py`) scans every `set_frame(...)` call site and asserts `.copy()` in the same expression.

The shim sweep at v2 closure confirmed clean: zero P0.6 migration scaffolding remains. The `_sync_set_cloud_state`, `_sync_mint_room`, `_sync_add_room_participant`, `_sync_clear_room`, `_sync_set_prev_det_count` functions are documented as **load-bearing public sync API** (NOT shims) — they're the canonical synchronous read/write entry points the pipeline needs for non-async contexts.

---

# Part XL — Typed Session State (P0.7)

## 261. Why Move the Session Dict to a Typed Store

`_active_sessions: dict[str, dict]` in `pipeline.py` carried the entire identity-evidence + voice-evidence + dispute-state + session-lifecycle model. Each per-person entry was a free-form dict with no schema. Code that touched a session field looked like:

```python
_active_sessions[pid]["dispute_set_at"] = time.time()
_active_sessions[pid]["recent_voice_confs"].append(conf)
del _active_sessions[pid]["cached_prefix"]
```

The cost:

- **No schema enforcement.** A typo (`displute_set_at`) silently created a new key. A field rename required grepping every call site.
- **No invariant guards.** A session could be in dispute state (`person_type == "disputed"`) without `dispute_set_at` being set — the auto-clear timeout (Part XV §106) would never fire.
- **Concurrent access.** Tests and background coroutines wrote to the same session dict without coordination.
- **No single-writer principle.** ~190 sites across `pipeline.py` and `test_pipeline.py` wrote directly to the session dict. Any future invariant (e.g. "the engagement gate must always set `bootstrap_credits` to N_INITIAL_VOICE_BOOTSTRAP") had to be defended at every site individually.

P0.7 builds `core/session_state.py` to fix this. The migration was non-trivial — a 5-phase staged sub-PR sequence (P0.7.1 → P0.7.5.D) that ran for ~10 days.

## 262. `core/session_state.py` — Three Dataclasses

```python
@dataclass(slots=True)
class VoiceEvidence:
    voice_match_conf:           float = 0.0
    voice_last_heard_ts:        float = 0.0
    voice_sample_count:         int = 0
    bootstrap_credits:           int = 0
    recent_voice_confs:         list[float] = field(default_factory=list)
    # ... 9 fields total

@dataclass(slots=True)
class Session:
    person_id:                  str
    person_name:                str
    person_type:                str
    started_at:                 float
    last_face_seen:             float = 0.0
    last_spoke_at:              float = 0.0
    dispute_set_at:             Optional[float] = None
    disputed_claimed_name:      Optional[str] = None
    prior_person_type:          Optional[str] = None
    disputed_block_count:       int = 0
    disputed_block_alerted:     bool = False
    voice_only_origin:          bool = False
    voice_face_confirmed:       bool = False
    cached_prefix:              Optional[str] = None
    core_memory:                Optional[dict] = None
    waiting_for_name:           bool = False
    room_session_id:            Optional[str] = None
    user_turns:                 int = 0
    evidence:                   VoiceEvidence = field(default_factory=VoiceEvidence)
    # ... 29 fields total

@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    """Immutable frozen snapshot for read-only access."""
    # Same 29 fields as Session, but every collection is replaced with a new copy
    # at snapshot time. Returned by SessionStore.peek_snapshot().
```

The slots-on-everything is load-bearing: it makes every field assignment a typo into an `AttributeError` at runtime, and it shrinks the per-session memory footprint substantially.

`SessionSnapshot` is the read-only contract. Anywhere in the codebase that needs to read session state (prompt assembly, scene block, KAIROS, brain context) calls `_session_store.peek_snapshot(pid)` and gets back a frozen snapshot whose internal collections are *copies* — mutating them has no effect on the underlying Session.

## 263. `SessionStore` — Single Owner with `asyncio.Lock`

`SessionStore` is the only writer of `_sessions: dict[str, Session]`. Every mutation is async and acquires `self._lock` before touching the dict. Every read is sync and returns either a SessionSnapshot or a plain value (for `peek_<field>` accessors).

The `peek_snapshot(pid)` and `peek_all_snapshots()` methods are sync by design. They copy the underlying Session into a frozen SessionSnapshot at peek time. The same-thread asyncio safety contract (§268) lets them skip the lock — within a single asyncio thread, mutations are serialised between `await` boundaries, so a sync peek can never see a half-mutated session.

## 264. The 21 Named Transition Methods

The migration's *real* value is the named transition methods. They replace ~190 ad-hoc dict mutations with semantically-meaningful operations:

| Method | What it does |
|---|---|
| `open_session(pid, name, person_type, ...)` | Create a fresh Session entry. Engagement-gate-passed callers pass `engagement_gate_passed=True` so `bootstrap_credits` are seeded. |
| `close_session(pid)` | Remove the Session entry. Idempotent — closing a missing session is a no-op. |
| `update_on_reopen(pid, voice_confidence, now)` | Re-open path: refresh voice match conf + last_spoke_at + last_face_seen in one atomic operation. |
| `transition_to_disputed(pid, claimed_name, reason, now)` | Capture `prior_person_type`, set `person_type="disputed"`, set `dispute_set_at`, set `disputed_claimed_name`. |
| `clear_dispute(pid, now)` | Restore `person_type` from `prior_person_type` (fail-closed to `"stranger"` if missing per P0.2). |
| `increment_block_count(pid)` | Bump `disputed_block_count` for the watchdog. |
| `mark_block_alerted(pid)` | Set `disputed_block_alerted=True` (idempotent — fires the watchdog alert exactly once). |
| `update_voice_heard(pid, conf, ts)` | Append to `recent_voice_confs` (with maxlen), update `voice_match_conf`, set `voice_last_heard_ts`. |
| `update_face_seen(pid, ts)` | Set `last_face_seen`. |
| `set_voice_only_origin(pid, value)` | Set the flag captured at engagement-gate pass for voice-only strangers. |
| `set_bootstrap_credits(pid, n)` | Seed bootstrap credits at engagement gate pass. |
| `decrement_bootstrap_credits(pid)` | Consume one credit on a voice-accumulation event. |
| `set_voice_face_confirmed(pid, value)` | Set the flag captured at progressive-enrollment gate pass. |
| `set_core_memory(pid, value)` | Cache the core-memory dict for prompt assembly. |
| `set_room_session_id(pid, rsid)` | Bind a session to a room (Part XXVI §163). |
| `bump_user_turn_count(pid)` | Increment turns for stranger-engagement gate progress. |
| `append_recent_attribution(pid, attr)` | Track the speaker-routing history for debug. |
| `set_cached_prefix(pid, prefix)` | Update the cached prompt prefix for compression. |
| `set_dispute_set_at(pid, ts)` | Anchor the dispute timeout (P0.2 fail-closed default of None means "no timeout yet"). |
| `set_waiting_for_name(pid, value)` | Track stranger-engagement state. |
| `set_person_name(pid, name)` | Rename within the session (after `update_person_name` tool fires). |

Every method has a focused contract. The methods *enforce invariants* — `transition_to_disputed` cannot be called without supplying a `reason`; `clear_dispute` cannot grant privileges higher than `prior_person_type`; `decrement_bootstrap_credits` returns False (no credit available) without mutating if credits are already zero.

## 265. `SessionSnapshot` — Frozen, Sliced, Cheap to Pass Around

The frozen dataclass is the read-only contract. Anywhere in the codebase that needs session state in a logging context, a prompt-assembly context, or a backround coroutine context, the call site does:

```python
_snap = _session_store.peek_snapshot(pid)
if _snap is None:
    return  # session closed
if _is_disputed(_snap):
    # ... handle dispute
```

Snapshots are cheap to create (29 field copies + a few list copies) and impossible to mutate (frozen). They're passed across `await` boundaries safely — the snapshot represents state at a specific point in time and the underlying Session can evolve freely afterwards.

`peek_all_snapshots()` returns a list of snapshots, one per active session. This is the iteration API for code that needs to scan every session (e.g. `_expire_stale_sessions`, the health log's per-session aggregate). The iteration is a snapshot of the dict at peek time; new sessions opened during iteration are not visible (consistent with the "snapshot represents a specific point in time" semantics).

## 266. The 5-Phase Migration (P0.7.1 → P0.7.5)

The migration ran in 5 staged sub-PRs, each one independently shippable:

- **P0.7.1** — Foundation. Build `core/session_state.py` with the three dataclasses + `SessionStore` with the named transition methods. No production wiring yet. 45 behavioral unit tests + 12 structural AST invariants in `tests/test_session_store.py` and `tests/test_session_state_invariants.py`. Autouse `_reset_session_state_between_tests` fixture in both conftest files. **+57 tests (1609 → 1666).**
- **P0.7.2** — Read-path migration. 12 production read sites in `pipeline.py` migrated from `_active_sessions[pid]["field"]` to `_session_store.peek_snapshot(pid).field`. Closure invariant test `tests/test_p072_read_migration_progress.py` AST-scans for unallowed reads and caps at 0. 3 documented dict-read keeps (`_compact_running`, `recent_attributions` ×2) where the deque mutation requires a mutable reference; those use the legacy access pattern with allowlist annotation.
- **P0.7.3** — Lifecycle write-path migration. `_open_session` re-open path, voice_only_origin backfill, core_memory capture, dispute-flip via `transition_to_disputed`, increment_block_count + mark_block_alerted, RIDM dispute path, auto-clear via `clear_dispute`. ~32 production write sites migrated.
- **P0.7.4** — Full migration cleanup. All 32 `_active_sessions[pid]["field"] = value` dual-write lines deleted. `SHIM_DISPATCH` dict deleted. `_shim_mirror_session_field_write` function deleted. All 21 `_shim_set_*` methods deleted from SessionStore. `ALLOWED_LEGACY_READS` emptied to `frozenset()`. Cap=0 in closure invariant test. `peek_all_snapshots()` added so `_expire_stale_sessions` iterates over snapshots instead of dict items.
- **P0.7.5** — Test suite restoration after the migration. ~152 test failures across `test_pipeline.py` and adjacent test files migrated from `_active_sessions` dict API to `_session_store` API (`open_session`, `transition_to_disputed`, etc. via `asyncio.run()`). Sub-PRs: P0.7.5.A (read migration backlog), P0.7.5.B (12 specific fixes), P0.7.5.C (19 session-open tests + production bug fix), P0.7.5.D (latent test regression — `test_update_system_name_rejected_on_empty_user_text_by_default` was passing by accident off residual state). Full suite restored to 1716 passing + 8 failing infra debt.

The staged sequence is the spec-first-review-cycle discipline (Part L §325) at work. Each sub-PR is small enough to review, large enough to make meaningful progress, and the validation gates between phases caught the migration backlog before it cascaded.

## 267. The SHIM Layer and Its Eventual Deletion

P0.7.2 and P0.7.3 used a shim pattern: every dual-write site (`_active_sessions[pid]["field"] = value`) was paired with a corresponding `_session_store._shim_set_<field>(pid, value)` call. The dual-write let the new store stay in sync with the legacy dict while the migration ran. Tests could exercise both paths independently.

P0.7.4 deleted the shims after every production read site was migrated. The cleanup was mechanical: 21 `_shim_set_*` methods deleted from SessionStore, 32 dual-write lines deleted from pipeline.py, the `SHIM_DISPATCH` dict deleted, the `_shim_mirror_session_field_write` helper deleted, the dead SHIM test file `tests/test_p072_session_store_migration.py` deleted (320 lines, 6 test classes — all testing now-deleted infrastructure).

The discipline learned: ship the SHIM with a deadline. The migration phase is when SHIM exists; the cleanup phase is when SHIM is deleted. Leaving SHIM in place "just in case" is the kind of half-finished migration that breeds the next decade of technical debt.

## 268. `peek_all_snapshots` and the Single-Thread-Asyncio Safety Contract

The contract: `peek_snapshot(pid)` and `peek_all_snapshots()` are sync methods that read `self._sessions` without acquiring the lock. They're safe because:

1. **Single asyncio thread.** All async mutations happen on the main asyncio thread. There's no thread pool writing to SessionStore.
2. **Mutations serialise between `await` boundaries.** When `async def set_x(...)` runs, it owns the lock and the field assignments happen synchronously between two `await` points. No other coroutine can interleave.
3. **Sync peek reads are atomic at the field level.** `Session.field` reads in CPython are GIL-atomic for built-in types. The peek returns a new `SessionSnapshot` constructed from a single pass through the fields — no mid-construction visibility.

The empirical proof: P0.6.4's behavioral race test (`test_voice_gallery_concurrent_write_read`) demonstrated the same property on `VoiceGalleryStore` — 1 writer thread + 1000 reader threads against a peek-read pattern produced zero `RuntimeError("dictionary changed size during iteration")` over 1000 cycles.

The contract is documented at the top of `core/session_state.py` so future maintainers don't try to "harden" the peek path with locks (which would break the cheap-read invariant) or to call peeks from a thread pool (which would break the single-asyncio-thread assumption).

## 269. Dispute State via Named Transitions

The dispute state machine (Part XV) used to be ad-hoc — code that wanted to flip a session to disputed wrote `_active_sessions[pid]["person_type"] = "disputed"` directly, possibly forgot to capture `prior_person_type`, possibly forgot to set `dispute_set_at`. P0.7.3 routed all three operations through `transition_to_disputed(pid, claimed_name, reason, now)`:

```python
async def transition_to_disputed(
    self, pid: str, claimed_name: Optional[str], reason: str, now: float
) -> None:
    async with self._lock:
        sess = self._sessions.get(pid)
        if sess is None: return
        sess.prior_person_type = sess.person_type
        sess.person_type = "disputed"
        sess.disputed_claimed_name = claimed_name
        sess.dispute_set_at = now
        # ... emit log
```

Three invariants enforced in one method: prior_person_type captured (P0.2 fail-closed default lands cleanly here), person_type flipped, dispute_set_at anchored. The auto-clear timeout (Part XV §106) now reliably has a timestamp to compare against.

`clear_dispute(pid, now)` does the inverse: restore `person_type` from `prior_person_type` (defaulting to `"stranger"` per P0.2 fail-closed), clear the dispute-tracking fields, log the resolution.

## 270. The Closure Invariants That Lock the Migration

P0.7's three closure invariants:

1. **`tests/test_p072_read_migration_progress.py`** — AST-scans for unallowed dict-read patterns on `_active_sessions`. Cap=0 means any new direct-read regression fails CI. Has 3 documented allowlist entries with explicit `# allowlist:` comments.
2. **`tests/test_session_store.py::TestSessionStoreClosure::test_no_dual_writes_remain`** — AST-scans for `_active_sessions[pid][<field>] = ...` assignments outside the test file. Cap=0.
3. **`tests/test_session_state_invariants.py::test_sync_mutator_allowlist`** — 12 structural tests. Verifies every method on SessionStore that mutates state is `async def`. Allowlist exempts `__init__` and `reset()`.

The combined effect: any future code path that wants to bypass SessionStore must explicitly opt out via the allowlist, and the allowlist is a small enumerable set that reviewers can audit.

---

# Part XLI — Per-Tool Timeout Protection (P0.8)

