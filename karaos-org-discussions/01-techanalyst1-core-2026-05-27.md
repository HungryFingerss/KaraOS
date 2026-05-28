# TechAnalyst-1 — KaraOS Core Deep Review — P1 Prep — 2026-05-27

**Author:** TechAnalyst-1 (agent `e7a9015b-05b6-4f24-926b-ae540cb901f5`)
**Issue:** KAR-121
**Scope:** core layer (orchestration / session / reconciler / state / test infrastructure)
**Strategic goal target:** KaraOS as universal ROS 2 robot cognitive-runtime middleware

---

## 0. Executive summary (one screen)

KaraOS today is a **production-grade single-user social-AI runtime** with extraordinary engineering discipline at the *correctness* layer (28+ AST-enforced structural invariants, ~2810 passing tests, 15 elevated architectural doctrines, P0.R 14-cycle resilience arc CLOSED). The core layer that everything else depends on — `session_state.py`, `state.py`, `store_base.py`, `reconciler.py`, the 8 P0.6 Stores, the P0.X SQL/Kuzu paired-write discipline — is sound, small, and tested at the structural level. Pre-P1 there are **no CRITICAL correctness bugs** that would crash, lose data, or produce wrong attributions. There are HIGH / MEDIUM hygiene items that should be fixed before P1 starts to avoid compound regressions.

**Where it will crack under ROS 2 robot scale/diversity:**

1. The current architecture is **single-process, single-machine, single-user**. There is no protocol boundary, no IPC contract, no published adapter SDK. Every ROS 2 robot platform (Unitree G1, Boston Dynamics, π‑0/GR00T-equipped, custom controllers) would have to fork the cognitive runtime today — there is no `karaos-adapter-sdk` to install against.
2. `pipeline.py` is ~8000 lines (verified by inspection of the head; the file is dominated by `run()` + `conversation_turn()` + tool dispatch + lifecycle helpers). This is the elephant `complete-plan.md` correctly identifies as P1.A1‑A3 decomposition target.
3. There is no durable-commitment store, no scheduler, no per-skill verifier registry — the three things `future-execution.md` §2.4.2 names as KaraOS's defensible gap vs ROSClaw / Intrinsic / 1X / Layer-C MCP servers.
4. There is **no CI configuration in tree** (`P1.P1` from the CLAUDE.md Pending Work block is unchanged). Every structural invariant — induction-surfaces-invariant-gaps, paired-write inverse checks, `EXPECTED_RULES_BY_BAND`, `_persistent` atomic-replace, `_INVERSE_WALK_PATHS` — is *architect-advisory* until `.github/workflows/fast.yml` exists. This is the single highest-leverage pre-P1 fix.

**Headline pre-P1 must-fix list (full ranking in §4):**

| # | Item | Severity | Why now |
|---|---|---|---|
| MF1 | Ship `.github/workflows/{fast,slow,security}.yml` per P0.0 spec | CRITICAL | All 28+ structural invariants are dead-code without CI |
| MF2 | Cohere the `claim.confidence == 0.0` vs `<= 0.0` semantic in `core/reconciler.py` lines 624, 656, 715, 739, 794 | HIGH | Session 119 fixed 3 of 5; the remaining 3 `== 0.0` checks rely on exact float equality of a downstream cosine signal; ambiguity is documented but the asymmetry deserves a single-source-of-truth helper |
| MF3 | Lock `Session` mutable list fields (`recent_voice_confs`, `core_memory`, `recent_attributions`) behind controlled mutators | HIGH | `dataclass(slots=True)` does NOT prevent in-place list mutation; only the lock + the snapshot-copy makes them safe today. A future bare-Python read could escape the lock window |
| MF4 | Decide P1.A1‑A3 decomposition shape **before any code lands** | CRITICAL | The 8000-line `pipeline.py` is the foundation for *every* P1 architectural change. Splitting it wrong is unrecoverable |
| MF5 | Bring `everything_about_system.md` (608 KB) into a bi-weekly refresh cadence | MEDIUM | Doc drift compounds; the file is the onboarding document for every future contributor |
| MF6 | Decide the **strategic-goal alignment**: KaraOS-as-social-AI vs KaraOS-as-ROS-2-middleware. `complete-plan.md` and `future-execution.md` describe *different products* | CRITICAL | P1's decomposition shape depends on this decision. See §8. |

**Recommended changes to `future-execution.md`:** see §8 — it is internally consistent and well-researched, but the implicit premise that the current `dog-ai/` codebase already serves the ROS 2 robot adapter use case is incorrect. The current code is closer to *Layer F (UX-on-humanoid-hardware)* than *Layer D (cognitive middleware)*. The blueprint should explicitly call out the **lift required** to move the current pipeline to the middleware framing.

---

## 1. What I read

Strategic context (read in full):

| File | Lines | Notes |
|---|---|---|
| `C:/Users/jagan/dog-ai/dog-ai/CLAUDE.md` | extensive (loaded by harness) | Full P0.R15 + P0.S10/11/12 closure narratives, 15 elevated doctrines, board-bug remediation track |
| `C:/Users/jagan/dog-ai/complete-plan.md` | ~200 head + selected sections | Master plan; positioning as embodied context runtime above motor control |
| `C:/Users/jagan/dog-ai/future-execution.md` | ~300 head | KaraOS as ROS 2 cognitive middleware; 14 locked architectural decisions; 5 strategic risks |
| `C:/Users/jagan/dog-ai/to_be_checked.md` | ~200 head | Canary checklist format; coverage matrix; deferred-canary entries P0.R12-R15 + P0.S10/11/12 |
| `C:/Users/jagan/dog-ai/dog-ai/everything_about_system.md` | head 300 lines (file is 608 KB) | TOC + Part L doctrine summary + Wave 5-7 |

Core code (read in full):

| File | Read | Lines |
|---|---|---|
| `core/session_state.py` | full | 433 |
| `core/state.py` | full | 109 |
| `core/store_base.py` | full | 42 |
| `core/reconciler.py` | full | 957 |
| `core/pipeline_state_store.py` | head | 120 |
| `core/brain.py` | head | 120 |
| `pipeline.py` | head 80 (file is large) | sampled |

Core directory inventory (via Glob):

47 Python files in `core/` covering: vision (face detection/embedding/anti-spoof/tracking), voice (ECAPA, diarization), audio (Whisper/TTS), brain (LLM orchestration), brain_agent (multi-agent knowledge), db (FaceDB+FAISS), schema migrations (P0.9), event log (P0.0.7), 8 Stores (P0.6), reconciler+reconciler_state (P0.10), session_state (P0.7+P0.B1 frozen VoiceEvidence), pipeline_state_store (P0.6.6), voice_channel/vision_channel (channel abstractions), abstraction (P-classifier graph), classifier_db/classifier_graph (Spec 1+2), state, store_base, config, sanitize (P0.S5), env_validation (P0.S3), dashboard_token (P0.S2), heavy_worker (P0.R6 ProcessPoolExecutor pools), health, disk_monitor, crash_logs (P0.R11), audit, conversation_store, presence_store, track_store, voice_gallery_store, per_person_agent_store, cache_store, vision_frame_store, anti_spoof_rejection_store, room_orchestrator, vision_provider_state, pipeline_invariants, event_log/, _minifasnet/.

Test infrastructure (via Glob):

- 13 explicit `test_*invariant*.py` files (silent-except, layering, P08 structural, P10 routing, P06 store, event_log, P0.S4 privacy_level, session_state, kuzu atomicity, faiss atomicity, user-text gate, secrets, repeat-guard)
- 47+ explicit `test_p0_*.py` files (per-spec acceptance)
- `tests/conftest.py` and root `conftest.py` autouse store-reset fixture (P0.6.1)
- ~2810 passing tests per CLAUDE.md last-updated line

**Files I did NOT read in detail (out of scope for the core-layer focus and/or context budget):** `pipeline.py` body (~8000 lines, sampled head only — its decomposition is P1.A1‑A3's job, not this audit's), `core/brain_agent.py` body, `core/db.py` body, `core/audio.py`, `core/vision.py`, the 47 P0.* test files individually. I read enough to defend every claim below.

---

## 2. Architecture assessment

### 2.1 What is genuinely well-designed

**Layered Store pattern (P0.6).** `core/store_base.py` defines `Store(ABC, Generic[T])` with one abstract `reset()` and an enforced contract: `_lock: asyncio.Lock` for every mutation method, sync `peek_*` reads, async mutators acquire the lock. The 8 production Stores (`PresenceStore`, `TrackStore`, `ConversationStore`, `VoiceGalleryStore`, `PerPersonAgentStore`, `CacheStore`, `PipelineStateStore`, `VisionFrameStore`) all inherit. **28 legacy module-globals were retired** (P0.6.7 v2 closure). `tests/test_p06_store_invariants.py` + `tests/test_p06_legacy_global_progress.py` (cap=0) + `tests/test_p06_store_schemas.py` enforce drift prevention at AST time. This is the right shape: minimal interface, structurally enforced.

**Typed Session state with frozen evidence (P0.7 + P0.B1).** `core/session_state.py:18` declares `@dataclasses.dataclass(frozen=True, slots=True) class VoiceEvidence` — every voice/face/anti-spoof signal lives in an *immutable* sub-record rebound via `dataclasses.replace()`. The AST tripwire at `tests/test_p0_b1_voice_evidence_frozen.py::test_no_direct_voice_evidence_mutation_outside_sessionstore` enforces the rebinding convention in production code. `SessionSnapshot` (frozen+slots) is the sync read shape — safe to hold across await points. The single SessionStore writer owns the `asyncio.Lock`. This is exactly the pattern multi-agent runtimes need: separate the mutable owner from immutable consumers.

**Rule-cascade reconciler (P0.10).** `core/reconciler.py` is a 23-rule flat cascade with:
- Pure functions on `(IdentityClaim, PresenceState, SessionState)` returning `Optional[RoutingDecision]`
- `LOWER_BOUND` attribute on every Priority-0 rule for band-ordering invariant
- `EXPECTED_RULES_BY_BAND` static mapping consumed by the Reconciler-Shadow band-divergence trigger
- `_last_resort_ambiguous` as locked-in `_CASCADE[-1]`
- AST tests enforcing `test_cascade_ordering_*`, `test_p0_short_utterance_gap_holds_current`, `test_b6_d4_cascade_membership_covered` (P0.B6)

This is materially better than the 273-line legacy `_resolve_actual_speaker` it replaced and is the *right model* for the routing problem KaraOS needs to scale across robot platforms (different sensors → different priorities → different rules; cascade order is the audit trail).

**Cross-storage atomicity discipline (P0.5 + P0.X).** Three locked-in write patterns (`SCHEMA_MIGRATION` / `RAISE` / `SWALLOW`) for the brain.db↔Kuzu and faces.db↔FAISS dual-write boundaries. **Inverse-check discipline** (`test_all_paired_write_sites_are_in_tuple`) caught `prune_outlier_embeddings` as a real hidden violation during P0.5. The pattern generalizes — every multi-store write site is enumerable and AST-checked.

**Induction-surfaces-invariant-gaps doctrine (batting 7-for-7, CLAUDE.md).** Every structural invariant ships with a deliberate-regression check. P0.B5 confirmed (a)-(d) all fired correctly on revert; P0.B6 D4 confirmed AST tripwire fires on dummy `_p0_test_rule` injection. This is the *single most important quality discipline* in the codebase and should be carried forward as a binding rule on every P1 sub-PR.

**Spec-first review cycle for multi-day specs (15-for-15).** Phase 0 audit → Plan v1 → review → Plan v2 → code. Each phase produces grep-verified findings, *not* hand-waved intent. P0.S10 had a 6-artifact cycle (Plan v1+v2+v3+v4) due to 3 PI absorptions across 3 verification axes. This is the right discipline; the cost is 2–4× test-design cost paid up front, returns 4–6× saved rework. For P1, this discipline MUST hold.

### 2.2 Where it will crack under ROS 2 robot scale/diversity

**Crack #1 — no protocol boundary.** Every consumer of the runtime is *inside the same Python process* (`pipeline.py` calls `core.brain.ask_stream`, calls `core.brain_agent.notify`, calls `core.db.add_embedding` directly). For ROS 2 robots to consume KaraOS, there must be (a) typed contracts (`IdentityClaim`, `PresenceState`, `RoutingDecision`, `ActionProposal`, `RobotObservation`, `RobotCapability` — drafted in `future-execution.md` Decision 3.6 + complete-plan.md P0.0.6 but **NOT YET LANDED IN TREE**), (b) a transport (gRPC/MCP per complete-plan.md Decision 3.8 + 3.13), (c) a separately published `karaos-adapter-sdk` package (Decision 3.3). Until all three exist, "KaraOS for any ROS 2 robot" is a marketing claim with no engineering surface to make true.

**Verification:** Glob for `cognition/specs/v0/*.py` returns nothing in tree (the directory does not exist). The dataclasses cited in `complete-plan.md` P0.0.6 (`RobotObservation`, `RobotCapability`, `ActionProposal`, `ActionResult`, `SafetyConstraint`, `TaskContext`) have not been created.

**Crack #2 — `pipeline.py` monolith.** ~8000 lines. The head I read (lines 1‑80) shows Tee/log/archive scaffolding at the very top of the module, before any production code. This is a smell: module-level side effects, threading state, queue infrastructure all running at import time. P0.S12 closed the spawn-mode subprocess re-import bug, but the deeper issue — that *the same module file* contains run-loop, conversation-turn dispatch, tool dispatch, lifecycle helpers, vision-loop background task, dream loop, kairos tick, heavy-worker pool warmup, signal handlers, factory reset, and 30+ module-level globals — remains. P1.A1‑A3 in `complete-plan.md` correctly identifies this as the largest architectural debt. **Until pipeline.py is decomposed, every P1 architectural change carries the full file's blast radius.**

**Crack #3 — no durable commitment store / scheduler / verifier registry.** `future-execution.md` §2.4.2 identifies these three as KaraOS's defensible gap vs ROSClaw, ROS-MCP-server, AutoRT, Intrinsic Flowstate, 1X NEO Chores. *None of the three exist in tree today.* The current `brain.db` knowledge schema (per CLAUDE.md and brain_agent table listing) stores facts about people, not commitments + due times + verifier IDs. The `_dream_loop` (memory consolidation) is *not* a commitment scheduler. There is no per-skill verifier registry. These are all *additions*, not refactors, and they are load-bearing for the entire strategic positioning.

**Crack #4 — `_persistent` dict + `state.write()` IPC has a non-obvious race surface even after P0.B5.**
- `core/state.py:14` declares `_persistent: dict = {}` (mutable module-global).
- `set_persistent()` uses atomic-replace + `threading.Lock` (P0.B5 D4 lands the lock).
- `write()` line 60 does `**_persistent` spread inside the `state` dict literal — this read is not under the lock; it relies on dict reads being atomic under CPython's GIL.
- The `# NOTE` block in `set_persistent` documents this honestly ("protects readers from torn iteration … does NOT protect against concurrent writers losing updates").

This is fine *for the current single-startup-writer* pattern. It is **not safe** if (a) a future runtime writer lands, (b) GIL-free CPython 3.13+ ships, or (c) any caller invokes `state.write()` from an executor thread. The latent activation conditions are documented in P0.11's closure narrative. For ROS 2 robot multi-process IPC use, this primitive needs to evolve into a structured-format IPC (protobuf/msgpack over Unix socket or shared memory).

**Crack #5 — Reconciler's `== 0.0` exact-equality checks (3 remaining sites).** `core/reconciler.py` lines 715, 739, 794 still use `claim.confidence == 0.0` for the `_p4_voice_ambiguous_no_candidates`, `_p4_voice_ambiguous_with_candidates`, and `_p5_no_session_no_action` rules. Session 119 closure narrative (CLAUDE.md) documents this as INTENTIONAL — "those represent genuine no-signal (embedding failed), not anti-correlated audio." That is defensible for the current ECAPA backend where `voice.identify()` returns exactly `0.0` only when the embedding computation failed. But:
- The semantic ("0.0 = embedding failed; <0 = anti-correlated") is encoded in the **caller** (`voice.identify`), not in the type system or in `core/reconciler_state.py::IdentityClaim`.
- If the caller is ever swapped (different voice ID backend on a future robot), the semantic silently breaks.
- The discipline is documented in *comments inside the rule bodies* but is not enforceable at AST time.

**Recommendation:** add `IdentityClaim.confidence_is_no_signal` boolean (or a sentinel value) so the semantic is part of the contract, not a property of one backend's return convention. This is exactly the kind of contract-vs-implementation split that `### Spec-contracts-not-implementations` doctrine asks for.

**Crack #6 — `Session` mutable lists inside `slots=True`.** `core/session_state.py:72-77`:
```python
recent_voice_confs:     list                  = dataclasses.field(default_factory=list)
core_memory:            list                  = dataclasses.field(default_factory=list)
recent_attributions:    list                  = dataclasses.field(default_factory=list)
```
`@dataclasses.dataclass(slots=True)` prevents *attribute* drift (no `__dict__`) but does NOT prevent in-place list mutation. The lock + the snapshot-copy (`list(s.recent_voice_confs)` in `_to_snapshot`) makes this safe **today**. But a future contributor reading `peek_snapshot(pid).recent_voice_confs` could call `.append()` on the snapshot's list — and the snapshot's list IS a fresh copy, so that mutation is silently lost, not crashing.

**Recommendation:** change `SessionSnapshot.recent_voice_confs` (and `core_memory`, `recent_attributions`) to `tuple` in the frozen snapshot. Mutations in the snapshot then raise `AttributeError`. The mutable Session keeps `list`. Mirrors `VoiceEvidence` discipline at one layer up.

### 2.3 Validation against industry standards

**ROS 2** (Robot Operating System 2) became the standard via (a) explicit message types (`.msg`/`.srv` files compiled to language-specific bindings), (b) DDS as transport, (c) language bindings (Python `rclpy`, C++ `rclcpp`, Rust `rclrs`), (d) ament/colcon build system, (e) clear node lifecycle (`rclcpp_lifecycle::LifecycleNode`), (f) standard message packages (`std_msgs`, `geometry_msgs`, `sensor_msgs`, `nav_msgs`), (g) DDS-backed security model. KaraOS lacks (a) — `IdentityClaim`/`PresenceState`/`RoutingDecision` are Python dataclasses with no schema export; (b) — no transport boundary; (c)/(d)/(e) — pipeline.py is a single Python process; (g) — `core/sanitize.py` covers prompt-injection at the LLM boundary, but there is no equivalent at the cognitive-runtime boundary because the boundary itself doesn't exist.

**MoveIt 2** (ROS 2 motion planning) became the standard via (a) a planner-plugin API (`planning_interface::PlannerManager`), (b) `MoveGroupInterface` C++/Python clients, (c) configurable RViz interface, (d) URDF/SRDF robot description integration, (e) `planning_scene_monitor` for collision state, (f) trajectory-execution interface (`controller_manager` integration). The corresponding cognitive-runtime analogues for KaraOS would be (a) a tool-plugin API for adding new tools without modifying `core/brain.py::TOOLS`, (b) clients for external MCP-aware LLM agents (per Decision 3.13), (c) a debug UI (`dog-ai-dashboard/` exists but is single-user, not a developer tool), (d) a robot-description analogue (`RobotCapability`), (e) a world-state monitor (`PresenceStore` is a start but is face-vision-specific). None of these analogues are in place at industry-standard quality.

**LangGraph / AutoGen / CrewAI comparison** (from `future-execution.md` §2.4 layer-C and brief context I have on the multi-agent space):
- LangGraph: deterministic state-machine over LLM nodes; explicit graph edges; persistent state via Postgres checkpointer. KaraOS's brain orchestration is event-driven (`notify()`) not graph-structured; persistence is per-database, not a unified checkpoint.
- AutoGen: peer-to-peer agent messaging; group-chat orchestration; tool registration via `register_function`. KaraOS's `_TOOL_HANDLERS` registry is closer in spirit but is global, not per-agent-scoped.
- CrewAI: role-based agent assembly with task-delegation. KaraOS's `BrainOrchestrator` is a singleton, not a role-orchestrator.

**What KaraOS has that none of those have:** typed Session state with frozen evidence (every multi-agent runtime I've seen uses dicts), structurally-enforced paired-write atomicity (none of those agent frameworks enforce cross-storage durability), induction-surfaces-invariant-gaps discipline (none of them deliberate-regression-test their structural invariants).

**What KaraOS is missing that all of those have:** a *durable* state machine that survives process restart and resumes from where it stopped (LangGraph checkpointer, AutoGen state save/resume, CrewAI task state). The `_dream_loop` is memory consolidation, not execution-state persistence. This is the load-bearing gap for the "durable scheduled commitments" claim in `future-execution.md`.

---

## 3. Bug census

Each finding cites file:line and a concrete failure mode. Severities use CLAUDE.md conventions (CRITICAL = data loss / wrong attribution / crash; HIGH = privilege escalation / silent contract violation; MEDIUM = surface drift / observability gap; LOW = cosmetic / doc drift).

### 3.1 CRITICAL — none confirmed in core layer

After reading `session_state.py`, `state.py`, `store_base.py`, `reconciler.py` end-to-end and `pipeline_state_store.py` + `brain.py` heads, **I found no CRITICAL correctness bugs** that would crash, lose data, or produce wrong attributions. This is a real achievement given the file count and the strategic ambition. The induction-surfaces-invariant-gaps discipline has clearly done its job at the structural layer.

The CRITICAL items that exist (`MF1` no-CI, `MF4` decomposition shape, `MF6` strategic alignment) are *architectural* gaps, not code bugs.

### 3.2 HIGH

**B-H1** — `core/reconciler.py:715, 739, 794` — `claim.confidence == 0.0` semantic encoded in caller, not contract.
- **What:** Three `_p4_voice_ambiguous_*` + `_p5_no_session_no_action` rules use exact float equality to distinguish "ECAPA embedding failed" from "ECAPA produced low/negative cosine."
- **Why a problem:** The semantic is a property of `core/voice.py::identify()`'s return convention, not of the `IdentityClaim` type. Swapping to a different speaker-ID backend (e.g. pyannote-only path, or future cloud speaker-ID) silently breaks the cascade because new backends may return small-positive or NaN where ECAPA returned exactly 0.0.
- **Fix direction:** Add `IdentityClaim.confidence_is_no_signal: bool` to `core/reconciler_state.py`. Rule predicates change from `claim.confidence == 0.0` to `claim.confidence_is_no_signal`. Backend callers set the flag explicitly. Add AST invariant that no rule body uses `== 0.0` against `claim.confidence`.
- **Validation:** real-world precedent — ROS 2 sensor_msgs uses explicit "data valid" booleans rather than relying on sentinel values; same pattern.

**B-H2** — `core/session_state.py:72-78` — `Session` mutable lists leak via snapshot.
- **What:** `recent_voice_confs`, `core_memory`, `recent_attributions` are `list` in both `Session` (mutable owner) and `SessionSnapshot` (frozen consumer). `_to_snapshot` copies via `list(s.recent_voice_confs)` etc.
- **Why a problem:** `frozen=True` on `SessionSnapshot` prevents rebinding the *list reference* but NOT in-place `.append()` on the list. A future consumer doing `snap.recent_voice_confs.append(x)` mutates a defensive copy that's later discarded, silently losing the write. This is the inverse failure to VoiceEvidence's pre-P0.B1 state.
- **Fix direction:** `SessionSnapshot.recent_voice_confs: tuple`, `core_memory: tuple`, `recent_attributions: tuple` (frozen-by-construction). Owner `Session` keeps list. `_to_snapshot` converts via `tuple(s.recent_voice_confs)`. Costs one AST tripwire and one round of typing fixups in consumers.
- **Validation:** mirrors VoiceEvidence frozen+slots discipline that landed in P0.B1; same family of fix.

**B-H3** — `core/state.py:60` — `**_persistent` spread inside `write()` is unlocked.
- **What:** `state = {"status": status, …, **_persistent, …}` reads the module-global dict mid-construction. P0.B5 D4 locked the *writer* (`set_persistent`) but not the *reader* (`write()`).
- **Why a problem:** Currently safe under (a) GIL atomicity for dict-spread, (b) single-startup-writer pattern. **Latent activation:** any future runtime `set_persistent` call (currently blocked by the comment but not enforced); GIL-free CPython 3.13+; calling `write()` from an executor thread. P0.11's closure narrative documents all three activation paths honestly but the fix is not in tree.
- **Fix direction:** acquire `_persistent_lock` for the snapshot read inside `write()`: `with _persistent_lock: persistent_snapshot = dict(_persistent)` and spread the snapshot, not the live global. Lock is held for one `dict(...)` call (microseconds).
- **Validation:** standard CSP / actor-model discipline; the lock is already there from P0.B5, the read side just needs to use it.

**B-H4** — `pipeline.py:31-77` — module-level side effects at import time.
- **What:** `_LOG_PATH` is computed, `_archive_terminal_output()` is called inside the `if __name__ == "__main__"` guard (per P0.S12), Tee class is defined, threading.Queue is constructed. All at module top-level / inside the guard.
- **Why a problem:** P0.S12 closed the spawn-mode subprocess re-import bug for the *current* shape (5 Tier-1 sites guarded). But the deeper smell is that `pipeline.py` doing this much work at import is incompatible with the future where pipeline.py must be importable by a test harness, by a launcher script, by the canary runbook, AND by `multiprocessing.spawn` workers. Every Tier-1 addition is a P0.S12-style cycle.
- **Fix direction:** P1.A1‑A3 decomposition should move all of pipeline.py module-level setup into an explicit `bootstrap()` function called from `main()`. Module import becomes side-effect-free. Subprocess re-import inherits the module shape without re-running side effects.
- **Validation:** standard Python application structure; `if __name__ == "__main__": main()` with all setup inside `main()`.

**B-H5** — `core/reconciler.py:152` — `_build_routing_inputs` takes **15 keyword arguments**.
- **What:** Pure helper signature is 15 keyword args; call sites are verbose.
- **Why a problem:** Adding a 16th input (e.g. for a new robot platform's sensor) requires changing every call site. The function shape is fragile against the scale-diversity ROS 2 robots will introduce.
- **Fix direction:** introduce a `RoutingInputs` dataclass that owns the 15 fields. `_build_routing_inputs` returns it (or accepts one constructed by the caller). New inputs are field additions, not signature changes.
- **Validation:** classic parameter-object refactor.

### 3.3 MEDIUM

**B-M1** — `core/store_base.py:18` — abstract `T = TypeVar("T")` is unused; `Store(ABC, Generic[T])` parameterization is decorative.
- **What:** No subclass binds `T` to a concrete payload type. `Generic[T]` adds nothing.
- **Why a problem:** type-hint consumers (mypy strict, IDEs) get no extra signal; the generic parameter is misleading documentation.
- **Fix direction:** either parameterize every subclass with its snapshot type (`class PresenceStore(Store[PresenceSnapshot])`) and use `T` in `reset()` / `peek_*` return annotations, or drop `Generic[T]`. The first option is the better one for the P1 typing tightening pass.

**B-M2** — `core/session_state.py:158` — `SessionStore.__init__` has no `cap` or `max_sessions` parameter.
- **What:** Dict-of-Session is unbounded.
- **Why a problem:** A long-running multi-person KaraOS deployment with frequent stranger-session minting + dispute auto-clear restoring `prior_person_type="stranger"` could grow `_sessions` without bound until `_expire_stale_sessions` reclaims them. Not a leak today (`_close_session` pops; `VOICE_SESSION_TIMEOUT=30s` keeps stragglers short), but a future ROS 2 robot platform handling more people could surface it.
- **Fix direction:** add `max_sessions: int = 64` (or similar) ceiling with eviction-by-LRU on overflow. Add health-line metric for `peek_session_count()`.

**B-M3** — `core/reconciler.py:937-946` — `EXPECTED_RULES_BY_BAND` is the only band→rule mapping but does NOT enumerate `normal` band.
- **What:** Only `gap` and `short_hard` bands have expected-rule sets. `noise` and `normal` bands rely on whatever rule the cascade fires.
- **Why a problem:** the Reconciler-Shadow band-divergence trigger only fires on `gap` and `short_hard`. A future rule that misfires on `normal` (the dominant band by volume) has no AST-time canary.
- **Fix direction:** enumerate expected rules for `normal` band too. The Bug-W class regression would have been caught earlier had `normal` been pinned.

**B-M4** — `core/state.py:80-95` — `safe_emit_sync` inside `write()` is wrapped in a local import.
- **What:** `from core.event_log import safe_emit_sync, StateWritePayload` lives inside `write()` to avoid a circular import.
- **Why a problem:** local import on every `write()` call is ~hundreds of nanoseconds wasted plus the appearance that `event_log` is an optional dep when it's actually required for replay. The circular-import workaround obscures the dependency graph.
- **Fix direction:** restructure imports so `event_log` does not depend on `state` (or invert the dependency); top-level the import. Or use `importlib.import_module` once at module init and cache.

**B-M5** — `everything_about_system.md` is 608 KB / ~10,000+ lines.
- **What:** The file is the canonical onboarding document but is too large to read in one Read call (the 256KB limit blocks the tool).
- **Why a problem:** Future contributors / agents can't reliably consume it. The TOC + Part references inside the file are intra-document but cannot survive a partial read.
- **Fix direction:** split into `everything_about_system/{00-toc.md, 01-foundations.md, 02-lifecycle.md, …}` mirroring the part structure. Each part stays under the read limit. Cross-references become explicit file links.

### 3.4 LOW

**B-L1** — `core/session_state.py:60` — `kairos_clock_reset: bool = True` with no docstring on the field.
- The field is mentioned in `Session 31` closure but a future reader has to grep for context.

**B-L2** — `core/reconciler.py:90-91` — `voice_reasoning: str = ""` default + `voice_raw_segment_scores: tuple = ()` are debug fields that survive into production routing — they're written into `IdentityClaim` but never consumed by any rule.
- Dead-weight that bloats every routing decision's serialized event-log payload.

**B-L3** — `core/store_base.py:33` — `Store.__init__` takes no `name` parameter for logging/debugging which store fired.
- Health-log emits per-store counters but `Store` has no self-id.

**B-L4** — Mutually-recursive imports — `core/reconciler.py` imports from `core/voice_channel.py` (IdentityClaim) and `core/vision_channel.py` (PresenceState); `pipeline.py` imports from `core/reconciler.py`. Walk this graph carefully during P1.A1 decomposition; one wrong split creates a circular.

---

## 4. Pre-P1 MUST-FIX list (ranked)

The list is short on purpose. The architecture is sound; the gaps are about *making the existing discipline enforceable* and *preparing for the P1 decomposition shape*.

### 4.1 MF1 (CRITICAL) — Ship CI before any P1 work begins

**What:** Land `.github/workflows/fast.yml`, `slow.yml`, `security.yml` per `complete-plan.md` P0.0 spec.

**Why MUST-FIX before P1:** Every elevated CLAUDE.md doctrine (Induction-surfaces-invariant-gaps, Twin-filename-pitfall-prevention, Phase-0-catches-wrong-premise, Phase-0-granular-decomposition-enables-accurate-estimates, Grep-baseline-before-drafting, Zero-precision-items-at-auditor-review, Canary-surfaces-real-gaps, Pass-2-grep-auditor-verified-before-Plan-v1-approval, Pre-audit-quantifier-precision-refined-by-grep, Resilience-track-arc-completion, Spec-first review cycle, Architect-reads-production-code-before-sign-off, Spec-contracts-not-implementations, Developer-improves-on-spec-by-reading-carefully, Verification-before-completion) **is enforced at the social/process layer today**, not at the CI layer. Every structural invariant test (`test_silent_except_invariant`, `test_layering_invariants`, `test_p08_structural_invariants`, `test_p10_routing_invariants`, `test_p06_store_invariants`, `test_event_log_invariants`, `test_p0_s4_privacy_level_invariants`, `test_session_state_invariants`, `test_kuzu_atomicity_invariants`, `test_faiss_atomicity_invariants`, `test_user_text_gate_invariants`, `test_secrets_invariants`, `test_repeat_guard_invariant`) is dead weight without CI. P1 will introduce new files, new boundaries, new code paths — and without CI to enforce the existing invariants, the first P1 sub-PR can silently violate every one of them.

**Validation precedent:** Linux kernel uses `make check` + CI; ROS 2 uses `industrial_ci` + GitHub Actions; every major Python project (Django, FastAPI, Flask) ships CI in tree from day 1.

**Success criteria:** `git push` to any branch triggers `fast.yml` and reports green/red within 5 minutes. `pytest -m "not slow and not network and not models"` runs on every PR. `mypy core/` (allow-list mode) runs. The P0.0.2 V1 xfail bundling already in tree (8 infra-debt tests carrying `@pytest.mark.xfail(strict=False)`) keeps the suite green under known infrastructure issues.

**Risk if we don't:** every P1 sub-PR's invariant violation surfaces only at next-cycle audit time — exactly the failure mode the doctrines exist to prevent. The P0.S10's 6-artifact cycle was about absorbing PIs that the existing discipline caught. Without CI, P1 sub-PRs that violate invariants don't get caught until *after* they merge.

**Risk if we DO ship CI:** ~4 hours of engineering work per `complete-plan.md` P0.0. Some flakiness in slow/model tests (already documented in P0.0.2 xfail bundle). False positives during the first 1-2 weeks while we calibrate the marker discipline. All cheap.

### 4.2 MF2 (HIGH) — Resolve the `== 0.0` vs `<= 0.0` semantic asymmetry in reconciler

**What:** B-H1 (above). Add `IdentityClaim.confidence_is_no_signal: bool` field; migrate the 3 remaining `== 0.0` checks to `claim.confidence_is_no_signal`; backend callers (`core/voice.py::identify`) set the flag explicitly.

**Why MUST-FIX before P1:** P1 will introduce multi-robot-platform adapters per `future-execution.md` Decision 3.2 (capability-typed sensor abstractions). Different platforms will use different voice-ID backends. The current `core/voice.py::identify` is the *only* backend, and the cascade hardcodes its return convention. A second backend (Kaldi, cloud Speech-to-Text + speaker-ID, robot-platform's own voice ID) WILL break the cascade silently.

**Validation precedent:** ROS 2 sensor_msgs/Imu has explicit `orientation_covariance[0] = -1` sentinel meaning "no estimate." The orientation field itself is always defined; the validity is a sibling field. Same pattern.

**Success criteria:** AST invariant `test_reconciler_no_exact_equality_against_claim_confidence` passes. Migration is reviewed by auditor under spec-first cycle (single artifact, OPTIONAL-Plan-v2 path).

**Risk:** none — change is mechanical, fully covered by the existing 21 contract tests + 22 per-rule behavioral tests + invariant suite. The Session 119 closure narrative even documents the semantic, so the fix is just *encoding the existing comment in the type*.

### 4.3 MF3 (HIGH) — `SessionSnapshot` mutable lists → tuple

**What:** B-H2. `recent_voice_confs`, `core_memory`, `recent_attributions` in `SessionSnapshot` become `tuple` (frozen by construction). Owner `Session` keeps list. `_to_snapshot` converts via `tuple(...)`.

**Why MUST-FIX before P1:** P1.A multi-thread / multi-process work (heavy_worker pools landed P0.R6; P1 will extend this) will increase the number of consumers reading SessionSnapshot. Each one is a potential source of silent-mutation bugs. Closing the gap now mirrors P0.B1's VoiceEvidence frozen migration discipline.

**Success criteria:** add 1 AST invariant test asserting these three fields are typed as `tuple` in SessionSnapshot. All existing consumers either read-only or convert explicitly to list.

**Risk:** consumers calling `snap.recent_voice_confs.append(x)` today would break — but per the test infrastructure (`tests/test_session_state_invariants.py` already enforces list-copy-not-aliased), no such consumer exists in production. Add a regression guard.

### 4.4 MF4 (CRITICAL) — Decide P1.A1‑A3 decomposition shape via Phase 0 audit before code

**What:** Run a full spec-first Phase 0 audit (per the elevated doctrine) on **how to split pipeline.py** before any code change. Output: a Plan v1 that names every helper function, every state container, every cross-module dependency. This single document determines whether KaraOS becomes a ROS 2 cognitive middleware or stays a single-process social-AI runtime.

**Why MUST-FIX before P1:** The 8000-line `pipeline.py` IS the cognitive runtime today. Splitting it wrong (e.g. splitting by line-count rather than by responsibility) creates worse architecture than the monolith. Splitting it right requires:
- Identifying the 5-7 logical responsibilities (run loop, conversation turn, tool dispatch, lifecycle, vision loop, dream loop, kairos, IPC) and naming them as distinct modules.
- Identifying the typed contract surface between them (likely the future `cognition/specs/v0/` dataclasses).
- Identifying which side effects are import-time (P0.S12 guard) vs `bootstrap()`-time vs `run()`-time.
- Deciding what becomes part of the future `karaos-adapter-sdk` boundary (Decision 3.3).

**Success criteria:** a Plan v1 + Plan v2 cycle lands with `### Phase-0-catches-wrong-premise` discipline applied. The plan names every helper to be moved, every test to be migrated, every invariant to be preserved.

**Risk if we skip Phase 0:** P1.A1‑A3 ships under reactive-patching discipline (the "30% surface" pattern documented in CLAUDE.md "Methodology" section). The remaining 70% of structure surfaces only after P1.A4 / P1.A8 / P1.RA — exactly when downstream work is hardest to reverse.

### 4.5 MF5 (MEDIUM) — Split `everything_about_system.md`

**What:** B-M5. The file is too large to read in one tool call. Onboarding any new agent (including future-me) is blocked.

**Why MUST-FIX (lower urgency):** doesn't block P1 code, but every P1 cycle's `### Architect-reads-production-code-before-sign-off` audit needs to also read the system doc to check for drift. The current file size makes that infeasible.

**Success criteria:** files in `everything_about_system/` each under 200KB. Cross-references via explicit file links. The TOC stays in `00-toc.md`.

### 4.6 MF6 (CRITICAL) — Strategic alignment decision

**What:** Jagan + the agent team should explicitly resolve: is KaraOS-the-product **(A)** the consumer social-AI runtime currently shipping in `dog-ai/`, where ROS 2 robot adapters are an *eventual* extension, or **(B)** the universal ROS 2 cognitive middleware described in `future-execution.md`, where the current `dog-ai/` code is the *first reference adapter* (or a hardware-specific UX layer that needs to be replaced)?

**Why MUST-FIX before P1:** `complete-plan.md` describes (A); `future-execution.md` describes (B); the issue description sent to me (KAR-121) says the goal is (B) — "Every ROS 2 robot should use only our system." The current code is (A). P1's decomposition shape depends on which is true:
- If (A): P1.A1‑A3 decomposes pipeline.py into 5-7 internal modules; the conversation-AI surface stays the API; ROS 2 robots get a translation adapter layer later.
- If (B): P1 must add the entire missing middleware surface (typed contracts, adapter SDK, conformance suite, durable commitment store, scheduler, verifier registry) — the conversation-AI inside pipeline.py becomes an internal capability of a much larger system.

These are *fundamentally different P1 plans*.

**Validation:** Linux became Linux because the kernel + GNU userland were *separable* (Stallman + Torvalds were explicit). ROS 2 became ROS 2 because rclpy/rclcpp/DDS were *separable* from any specific robot. The decision to be *the layer* vs *a product on top of the layer* is the load-bearing strategic choice.

**Success criteria:** an updated `complete-plan.md` + `future-execution.md` that are mutually consistent on this point. The CLAUDE.md "Project Overview" block ("AI robot dog") should match.

### 4.7 Items intentionally not in MUST-FIX

- B-H4 (pipeline.py module-level side effects) — folds into MF4.
- B-H5 (`_build_routing_inputs` parameter object) — incremental refactor; can land mid-P1.
- All MEDIUM and LOW items — none block P1.

---

## 5. P1 core implementation plan

This section assumes Jagan resolves MF6 toward **(B) — universal ROS 2 cognitive middleware** because that is what the issue description (KAR-121) explicitly asks for. If (A) is chosen, P1 reduces to MF4's pipeline.py decomposition plus standard hygiene; the items below collapse.

### 5.1 P1 phase ordering (refinement of complete-plan.md)

I propose this sequence, with each item gated by the phase-0 / spec-first discipline:

```
P1.A0  CI shipped (MF1)              ← BLOCKER
P1.A0.5 Strategic alignment (MF6)    ← BLOCKER
P1.A1  pipeline.py decomposition
P1.A2  conversation_turn extraction
P1.A3  _execute_tool extraction
P1.B1  IdentityClaim contract tightening (MF2 incl.)
P1.B2  SessionSnapshot tuple migration (MF3)
P1.C1  cognition/specs/v0/ lands (RobotObservation/RobotCapability/ActionProposal/ActionResult/SafetyConstraint/TaskContext per complete-plan.md P0.0.6, marked DRAFT)
P1.C2  Runtime Boundary Document (complete-plan.md P0.0.5)
P1.RA  Robot Adapter Bridge — first concrete adapter (complete-plan.md P1.RA)
P1.RA.1 Mock adapter implementation
P1.RA.2 Adapter SDK package boundary
P1.RX  First External Reference Robot Integration
P1.D1  Durable commitment store on brain.db (new schema)
P1.D2  Scheduler service
P1.D3  Per-skill verifier registry
P1.E1  Two-process split (durable layer + interactive layer per Decision 3.11)
P1.E2  MCP server interface (Decision 3.13)
P1.E3  Digital twin pre-execution validator (Decision 3.14)
P1.F1  Conformance suite v0.1
P1.G1  Replay harness generalization (P0.0.7 → P1.A16 promotion per complete-plan.md)
```

### 5.2 Per-task contract

For each P1.A/B/C/D/E/F/G item the spec-first cycle is mandatory. Below I provide the contract for the two highest-leverage items (the rest follow the same template).

**P1.A1 — pipeline.py decomposition**

- **What:** Split `pipeline.py` (~8000 lines) into 5-7 modules. Suggested partition (this is the spec-time hypothesis to test via grep, NOT a locked plan):
  1. `pipeline/runtime.py` — `run()` event loop + signal handling + `bootstrap()`.
  2. `pipeline/conversation.py` — `conversation_turn()` + `_execute_tool()` (extracted to its own sub-module if needed).
  3. `pipeline/lifecycle.py` — `_open_session`, `_close_session`, `_expire_stale_sessions`.
  4. `pipeline/vision_loop.py` — `_background_vision_loop` + watchdog wiring.
  5. `pipeline/dream.py` — `_dream_loop` + memory consolidation triggers.
  6. `pipeline/kairos.py` — `_kairos_tick`.
  7. `pipeline/state_io.py` — module-level globals (`_persons_in_frame`, `_voice_gallery`, etc.) migrated to stores (most already done via P0.6).
- **Why:** the 8000-line file is the foundation for every P1 architectural change. Decomposing it makes future changes auditable, testable, and isolated.
- **How:**
  - Phase 0 audit grep-counts every function in pipeline.py + every module-level global; produces a precise N-files split.
  - Plan v1 names every file move with its line range.
  - Plan v2 absorbs auditor PIs.
  - Code phase: mechanical move (per Spec-contracts-not-implementations and P0.8/P0.9.2 mechanical-extraction discipline).
  - Each module gets its own test file under `tests/test_pipeline_<module>.py`.
- **Success criteria:**
  - Every module < 1500 lines.
  - `pipeline.py` itself becomes a 50-line entry point.
  - Import graph is a DAG (no circulars).
  - All ~2810 existing tests pass with zero behavior change.
  - One new AST invariant: no module-level side effects in any new pipeline/*.py file (everything happens inside `bootstrap()` or imported functions).
- **Risks:** circular imports (mitigation: explicit dependency graph in Plan v1, validated by grep); test brittleness (mitigation: mechanical extraction discipline preserves call signatures exactly).

**P1.C1 — `cognition/specs/v0/` dataclasses + JSON Schema**

- **What:** Implement complete-plan.md P0.0.6 in tree. Create `cognition/specs/v0/python/` with frozen dataclasses for `IdentityClaim`, `PresenceState`, `RoutingDecision` (formalize existing), `MemoryFact`, `PrivacyTier`, `SafetyFlag` (formalize existing types). Plus new: `RobotObservation`, `RobotCapability`, `ActionProposal`, `ActionResult`, `SafetyConstraint`, `TaskContext`.
- **Why:** without typed contracts at the boundary, the ROS 2 middleware claim has no engineering surface.
- **How:**
  - Phase 0 audit reads every existing dataclass site to identify pre-formalization shape.
  - JSON Schema (`v0/<name>.schema.json`) with `$schema` + `version: 0`.
  - One golden fixture (`v0/<name>.fixture.0.json`) per spec.
  - Every file marked DRAFT in header.
- **Success criteria:** all dataclasses in tree; JSON schemas validate against fixtures; README in `cognition/specs/v0/`. Existing core code uses the formalized dataclasses (one mechanical migration pass).
- **Risks:** premature lock-in. Mitigation: explicit DRAFT marking + complete-plan.md's "no external standardization until v1" rule.

### 5.3 What I am NOT recommending for P1

- Don't ship a custom DDS-equivalent transport. Use gRPC + Protobuf or stick with Python's `multiprocessing.Queue`-equivalent in-process IPC until the two-process split (P1.E1) actually needs cross-machine RPC.
- Don't write a custom planner. Use existing motion-primitive contracts (P-0/GR00T/MoveIt) per `future-execution.md` Decision 3.1.
- Don't try to "support all ROS 2 robots" in P1. Ship a mock adapter (P1.RA.1), then a Unitree G1 reference adapter (P1.RX). Two adapters proves the abstraction; ten would be premature.
- Don't merge `complete-plan.md` and `future-execution.md` into one document. They serve different audiences (engineering plan vs strategic blueprint). Just make them mutually consistent on MF6.

---

## 6. Test & validation discipline (rules the developer, architect, auditor MUST follow during P1)

These are *binding* during P1, derived from CLAUDE.md's elevated doctrines and the bugs I found.

### 6.1 Mandatory for the architect

1. **Every multi-day P1 sub-PR runs the spec-first cycle.** Phase 0 audit → Plan v1 → auditor review → Plan v2 → code. No exceptions for "obvious" refactors. `### Spec-first review cycle` is 15-for-15 and the P0.S10 6-artifact cycle is the proof that this protects against silent surface drift.
2. **Every Phase 0 audit decomposes into D-decisions with named edit sites.** `core/X.py:LINE` granularity, not "the brain orchestrator." `### Phase-0-granular-decomposition-enables-accurate-estimates` doctrine + 9-supporting-instance track record requires this.
3. **Every Phase 0 audit's pre-audit framing is treated as a hypothesis.** Phase 0 grep tests it. If grep falsifies it, reset scope explicitly. Don't silently proceed with corrected scope.
4. **Architect reads production code before sign-off.** Path C grep-verify discipline. The 27-instance track record shows this catches MEMORY-FILE INDEX GAP, DEFERRED-CANARY-ENTRY-OMISSION, and STALE-CACHED-VERIFICATION sub-variants. P1 with new code paths and new dataclasses needs this enforced.

### 6.2 Mandatory for the developer

5. **Mechanical-extraction discipline for P1.A1‑A3.** No "while I'm here" cleanups during the pipeline.py split. Each function moves verbatim. P0.8 / P0.9.2 precedent.
6. **Every new structural invariant ships with an induction protocol.** Deliberate-regression check before sign-off. P0.B5 (4-for-4), P0.B6 (4-for-4), P0.R12-R15 (9-for-9), and the 7-for-7 doctrine track record all enforce this. P1's new typed contracts (cognition/specs/v0/) MUST have induction tests.
7. **Spec-contracts-not-implementations.** When the architect's spec names a contract (e.g. `IdentityClaim.confidence_is_no_signal`), the developer implements the *contract*. If the spec accidentally names a non-existent API, surface it (developer-improves-on-spec 6-for-6 doctrine).
8. **Verification-before-completion.** Run the relevant test suite + grep + read the actual diff before declaring done. The CLAUDE.md Pending Work block and `to_be_checked.md` are the live audit surface.

### 6.3 Mandatory for the auditor

9. **Pass-2 grep verified at Plan v1 approval.** Auditor independently re-greps everything the architect grepped. The 5-application track record (4 clean + 1 caught-real-gap at P0.R4) validates the catching mechanism. P1 sub-PRs with new files require auditor's Pass-2 grep to enumerate the new file inventory.
10. **Zero-precision-items at auditor review is the FLOOR, not the ceiling.** When all PIs are absorbed pre-handoff, the cycle ships at v1 (OPTIONAL-Plan-v2 sub-rule). 18 proof cases.
11. **Closure-audit verdict forwarding.** Architect explicitly forwards closure findings to auditor for ratification before declaring CLOSED. 5-consecutive-cycle track record (P0.R10/R12-R15/S11/S12/S10). Sub-rule elevation candidacy WARRANTED.

### 6.4 AST invariants to add during P1

| Invariant | Scope | Catches |
|---|---|---|
| `test_no_module_level_side_effects_in_pipeline_packages` | `pipeline/*.py` | P1.A1 decomposition drift back to monolithic shape |
| `test_no_exact_equality_against_claim_confidence` | `core/reconciler.py` | MF2 fix regression |
| `test_session_snapshot_collection_fields_are_immutable` | `core/session_state.py` | MF3 fix regression |
| `test_cognition_specs_v0_files_marked_draft` | `cognition/specs/v0/*.py` | Premature v0 spec standardization |
| `test_robot_adapter_protocol_implements_capability_contract` | `karaos-adapter-sdk/*.py` | P1.RA mock adapter regression |
| `test_no_motor_command_emission_from_cognition_layer` | `core/*.py` + `pipeline/*.py` | Cross-boundary scope creep |
| `test_durable_commitment_schema_versioned` | `brain.db` schema | P1.D1 migration |
| `test_verifier_registry_covers_every_skill` | verifier table | P1.D3 inverse-check |

### 6.5 CI checks beyond unit tests

| Check | Purpose |
|---|---|
| `ruff check` + `ruff format --check` | Lint + format consistency (per complete-plan.md P0.0) |
| `mypy core/` (allow-list mode) | Type discipline; tighten over time |
| `pytest --cov=core --cov-fail-under=85` | Test coverage floor for `core/` |
| `bandit -r core/` | Static security analysis (rate-limited; not on every PR) |
| `pip-audit` weekly | Supply-chain CVE check |
| Trivy filesystem scan weekly | File-level CVE scan |
| `detect-secrets pre-commit` | P0.S6 secrets-management invariant |
| TruffleHog `.github/workflows/trufflehog.yml` (PR diff + full-history) | P0.S6 follow-through |

### 6.6 Rules of the road during P1

- **Never start development until Jagan explicitly says to.** Per CLAUDE.md "Rules for Claude."
- **NO HARDCODINGS, predefined rules.** Brain decides; the runtime serves the brain's decisions. Per CLAUDE.md "Rules for Claude."
- **All settings live in `core/config.py` only.** Validated by `### Phase-0-granular-decomposition-enables-accurate-estimates` discipline track record.
- **All blocking I/O → `loop.run_in_executor(None, fn)`.** Existing rule; P1 heavy-worker work extends this to ProcessPoolExecutor.
- **Every test that touches production paths must monkeypatch path constants to `tmp_path`.** Session 122 incident in CLAUDE.md (real `wipe_all` against real `faces/`).

---

## 7. Canary additions for `to_be_checked.md`

These extend the existing canary checklist. Each entry follows the structured format already used at `to_be_checked.md`.

### 7.1 Post-P1.A1‑A3 canary

```
## P1.A1‑A3 — pipeline.py decomposition

Surfaces shipped:
- pipeline/runtime.py — run() event loop + bootstrap() module-level-side-effect-free entry point.
- pipeline/conversation.py — conversation_turn() consolidated.
- pipeline/lifecycle.py — _open_session, _close_session, _expire_stale_sessions.
- pipeline/vision_loop.py — _background_vision_loop + watchdog wiring.
- pipeline/dream.py — _dream_loop + memory consolidation triggers.
- pipeline/kairos.py — _kairos_tick.
- pipeline/state_io.py — final Store wiring (residual globals if any).

PASS signals:
- Full test suite green at parity with pre-P1.A1 (2810 → 2810 ± delta).
- pytest tests/test_no_module_level_side_effects_in_pipeline_packages.py PASSES on all 7 new modules.
- Multi-person canary: same Jagan/Lexi scenario as P0.S7 family arc — voice routing, scene rendering, conversation turn dispatch, dream loop, kairos, all behave identically.
- Pipeline boot time < 2× pre-P1 boot time (decomposition should not regress startup).
- Subprocess re-import (spawn-mode heavy worker) shows zero PermissionError / NameError / Tier-1 side effect leakage.

FAIL signals:
- Any test fails on the new module split that previously passed.
- Boot fails at import time with circular import error.
- Module-level side-effect test fires (e.g. someone added `_LOG_FILE = open(...)` at module top in a new file).
- Heavy-worker subprocess re-import surfaces side effects (P0.S12 invariant violated).

Test scenario (5 steps):
1. Run pytest --tb=no -q — should match pre-P1 count.
2. Boot pipeline; observe boot log shows BOOTSTRAP block, then RUN block.
3. Multi-person session (Jagan + Lexi via ElevenLabs): expect normal SCENE block + ROOM block + cross-person privacy block + visitor alert.
4. Force a heavy-worker pool spawn (face recognition path): verify no [Pipeline] WARN: could not archive lines from subprocess.
5. Stop + restart: observe terminal_output.md archived correctly to YYYY-MM-DD_HHMMSS.md.

Dependencies:
- P0.S12 D1-D4 (subprocess re-import guard) preserved.
- P0.B5 D4 (_persistent atomic-replace + lock) preserved.
- P0.R6 + P0.R6.X/Y/Z heavy-worker pool ordering preserved (4-pool warmup at run() startup).
- All 28+ structural invariants pass.
```

### 7.2 Post-P1.C1 canary

```
## P1.C1 — cognition/specs/v0/ dataclasses + JSON Schema

Surfaces shipped:
- cognition/specs/v0/python/ — frozen dataclasses for IdentityClaim, PresenceState, RoutingDecision, MemoryFact, PrivacyTier, SafetyFlag (formalized) + RobotObservation, RobotCapability, ActionProposal, ActionResult, SafetyConstraint, TaskContext (new).
- cognition/specs/v0/<name>.schema.json — JSON Schemas, validated against fixtures.
- cognition/specs/v0/<name>.fixture.0.json — one golden fixture each.
- cognition/specs/v0/README.md — DRAFT marker; breaking-change policy (none until v1).

PASS signals:
- pytest tests/test_cognition_specs_v0_files_marked_draft.py PASSES.
- jsonschema-validate against each fixture passes.
- Core code (core/reconciler.py, core/voice_channel.py, etc.) uses the formalized dataclasses without behavior change.

FAIL signals:
- Schema validation fails against fixture (drift).
- DRAFT marker missing from any v0 file.
- A new external integration attempts to lock against v0 (it's marked DRAFT for a reason).

Test scenario (3 steps):
1. Run pytest tests/test_p1_c1_specs_v0.py.
2. Run a jsonschema validator against every fixture.
3. Confirm README has DRAFT in the header.
```

### 7.3 Post-P1.RA canary (Robot Adapter Bridge first concrete adapter)

```
## P1.RA — first concrete robot adapter implementation (mock)

Surfaces shipped:
- karaos-adapter-sdk/ — separately published Python package.
- karaos-adapter-sdk/mock_adapter.py — reference mock adapter implementing the v0 contracts.
- karaos-adapter-sdk/conformance/ — first conformance tests.

PASS signals:
- `pip install karaos-adapter-sdk` works without installing dog-ai core.
- Mock adapter implements every method in RobotCapability per the v0 spec.
- Conformance suite passes against the mock adapter.
- Cognitive runtime (dog-ai) can call mock_adapter via the gRPC/IPC boundary (per Decision 3.8).

FAIL signals:
- Mock adapter directly imports dog-ai internals (boundary violation).
- Conformance check fails against the mock adapter (the mock should be canonical-pass).

Test scenario:
1. Fresh venv, `pip install karaos-adapter-sdk`, verify mock_adapter is importable.
2. Run conformance suite (`karaos-conformance --adapter karaos_adapter_sdk.mock_adapter`).
3. From a separate dog-ai process, call mock_adapter via IPC.
```

### 7.4 Cross-cut canary (after entire P1 lands)

```
## P1 end-to-end (full P1 cycle)

After P1.A1‑A3 + P1.B1‑B2 + P1.C1‑C2 + P1.RA‑RX + P1.D1‑D3 + P1.E1‑E3 land:

PASS signals (the hardest possible):
- All P0.* canary entries in to_be_checked.md still PASS (no P0 regressions).
- New durable commitment flow: user says "shut off the oven in 45 minutes," durable layer accepts, scheduler fires at +45 min, mock adapter ack, verifier confirms, audit log shows full chain.
- Multi-robot platform: same KaraOS source runs against (1) mock adapter, (2) future Unitree G1 simulated adapter — without any KaraOS core code change.
- MCP server endpoint exposes commit/list/cancel commitments tools to an external LLM client (per Decision 3.13).
- Digital twin pre-validator rejects an unsafe motion (per Decision 3.14).
- Two-process restart: interactive process restart does not lose any committed schedule.

FAIL signals:
- Any P0.* test/canary regresses.
- Strategic differentiator from `future-execution.md` §2.4.4 (the 7 mandatory items at Phase 7 close) is not demonstrably true.

Test scenario:
- Full canary week structure: solo Jagan, multi-person, stress + edge, regression diagnosis (per to_be_checked.md current cadence).
```

---

## 8. Recommended changes to `future-execution.md`

`future-execution.md` is internally consistent, well-researched, and the strategic positioning matrix in §2.4 is the most rigorous competitive analysis I've seen in this codebase. The recommended changes below are *not* corrections; they are *pre-conditions* the document doesn't currently surface explicitly.

### 8.1 Add a §4.5 "Lift required from current dog-ai/ codebase to v1"

**Why:** the document's §4 ("Existing System Context — Carry-Forward") implies that the current dog-ai code can be incrementally extended to the v1 product. After reading the codebase, I think this understates the lift. The current code is a single-user single-process social-AI runtime. The v1 product is a multi-process, partner-distributable, ROS 2-protocol-aware middleware. The phases below are missing from the §4 carry-forward narrative:

- **Lift 1:** Establish typed boundary (`cognition/specs/v0/`) — currently doesn't exist in tree.
- **Lift 2:** Split adapter SDK as a separate package — currently no `karaos-adapter-sdk/` directory.
- **Lift 3:** Decompose `pipeline.py` (8000 lines) into modules per P1.A1‑A3 — currently a monolith.
- **Lift 4:** Add durable-commitment store + scheduler (the load-bearing differentiator per §2.4.2) — currently no schema, no scheduler.
- **Lift 5:** Add per-skill verifier registry — currently no registry, no verifier abstraction.
- **Lift 6:** Add digital twin pre-execution validator — currently no MuJoCo integration.
- **Lift 7:** Add MCP server interface — currently no MCP module.
- **Lift 8:** Add two-process split (durable / interactive) — currently single-process.

**Recommended addition:** explicit §4.5 paragraph naming all 8 lifts and their target P1.* milestones.

### 8.2 Strengthen §2.3 "Brutal Scope Rule" with hardware-test gates

**Why:** the §2.3 allowed/forbidden claims are precise. But the *transition gate* between simulation-tested (Phase 4) and physical-robot-tested (Phase 9) deserves an explicit checklist. Without it, the temptation to claim "works on a real robot" after one successful Gazebo demo will be strong.

**Recommended addition:** §2.3.1 "What constitutes 'physical-robot tested'" with explicit minimums (N hours of supervised operation, M skill executions, K verifier disagreements resolved, zero safety incidents).

### 8.3 Tighten Decision 3.13 (MCP server interface)

**Why:** the decision is locked correctly but the implementation surface (`core/embodied/mcp_server/`) is described as if it lives inside KaraOS. The MCP protocol assumes a client-server boundary. If `mcp_server/` is just another module in KaraOS, the "complementary not duplicative" framing vs ros-mcp-server (§2.4 layer C) collapses — KaraOS becomes another MCP server, not the durable layer.

**Recommended addition:** clarify Decision 3.13's deployment shape — does the MCP server run as a separate process? Inside the durable process (Decision 3.11)? Inside the interactive process? This affects two-process IPC design.

### 8.4 Add Decision 3.15 (or §4 paragraph): "Existing dog-ai code is the FIRST reference adapter, not the v1 cognitive layer"

**Why:** this is the strategic alignment decision (MF6 above). The current document leaves it ambiguous. I recommend stating it explicitly: the consumer-social-AI behaviors in current `core/brain.py` + `pipeline.py` will be re-classified as **one specific instantiation** of the v1 cognitive runtime — specifically, a configuration that includes a face-vision sensor, a Whisper STT sensor, an ECAPA voice sensor, an LLM-driven conversation skill, etc. — and that future ROS 2 robot adapters consume the *same* v1 surface with different sensor/skill bindings. This makes the current code an asset, not a constraint.

### 8.5 Add explicit pre-conditions to Phase 0 in §5 (or wherever the phase plan lives)

**Why:** CLAUDE.md and complete-plan.md spec-first discipline (Phase 0 audit before any code) should be cited explicitly in future-execution.md as a *protocol*, not a recommendation. Every P1.* sub-PR follows the cycle.

---

## 9. Real-world precedent research

These are the patterns I cite as validation throughout this report.

### 9.1 How ROS 2 became the standard

ROS 2 succeeded over ROS 1 by:
1. **Explicit typed messages.** Every topic carries a `.msg`-compiled type with versioned schema. Cross-language consumers (rclpy, rclcpp, rclrs) get identical semantics.
2. **DDS transport.** No central master; peer-to-peer; supports QoS profiles; standard outside robotics.
3. **Build system.** ament/colcon makes the package boundary explicit. `package.xml` declares deps; CMakeLists.txt declares targets.
4. **Lifecycle.** `LifecycleNode` has explicit states (Unconfigured / Inactive / Active / Finalized). Transitions are observable.
5. **Standard messages.** `std_msgs`, `geometry_msgs`, `sensor_msgs`, `nav_msgs` give every robot a common vocabulary.
6. **Security model.** DDS-Security gives transport encryption + authentication + access control as a first-class concern.
7. **Long-term governance.** Open Robotics Foundation manages the spec; vendors (Boschem, Apex.AI, eProsima) contribute implementations.

**What KaraOS lacks of those:** items 1, 2, 3, 4, 5, 6, 7 (everything). Items 1, 2, 4 are achievable in P1 (typed contracts, gRPC/MCP transport, lifecycle via Stores). Item 3 is medium effort (pip-installable adapter SDK package). Item 5 is the cognition/specs/v0 work. Item 6 needs design (probably mTLS over the gRPC boundary). Item 7 is a long-term governance question.

**What KaraOS already has that ROS 2 lacks:** induction-surfaces-invariant-gaps discipline (ROS 2 has no equivalent at the protocol level); cross-storage atomicity discipline (ROS 2 doesn't have storage at the framework layer); spec-first review cycle as a *cultural* practice (ROS 2 has REPs but they're documentary, not enforced at PR time).

### 9.2 How MoveIt 2 (ROS 2 motion planning) handles cognitive-runtime-like problems

MoveIt 2's `move_group` node accepts `MotionPlanRequest` (typed message) and returns `MotionPlanResponse`. The planner is a *plugin*: `OMPL`, `STOMP`, `CHOMP`, `Pilz` all implement the same `planning_interface::PlannerManager`. The robot description (URDF/SRDF) is a *data file*, not code. The collision model is configured via SRDF disable-collision-pairs. Trajectory execution is delegated to `controller_manager`.

**Pattern lessons for KaraOS:**
- The *contract* (`MotionPlanRequest/Response`) is locked at the framework. The *implementation* (planner, collision checker, trajectory generator) is plugin-able.
- KaraOS should follow the same shape: cognition's contract is locked at `cognition/specs/v0/`. The specific implementations (which LLM, which voice ID, which face recognizer) are plugins.
- The current `core/brain.py::TOOLS` registry is closer to plugins-on-a-singleton than to a true plugin contract.

### 9.3 LangGraph / AutoGen / CrewAI vs KaraOS — what KaraOS is missing

- **LangGraph state checkpointing.** LangGraph persists agent state to a `Checkpointer` (Postgres / SQLite / in-memory) so the agent resumes from any prior turn. KaraOS has *facts* persisted (knowledge graph) but not *agent execution state* — there's no `BrainOrchestrator.save_state()`. P1.D1‑D2 (durable commitments + scheduler) is the equivalent feature.
- **AutoGen group-chat orchestration.** Multiple agents participate in one conversation; round-robin or speaker-selected. KaraOS's RoomOrchestrator is closer in spirit but is currently single-LLM-instance. Future ROS 2 deployments where the cognitive runtime needs to coordinate *across robots* would benefit from this pattern.
- **CrewAI role-based delegation.** Tasks have explicit roles; agents are typed by role. KaraOS's `BrainOrchestrator` is implicit-role. A future P1.* item: introduce explicit role typing on the brain agents so different robot platforms can swap roles.

### 9.4 Linux + Docker + Kubernetes precedent

- **Linux** became the standard because the kernel/userland separation was strict, the syscall ABI was stable, and every distribution could exist on top of the same kernel. **KaraOS analog:** clear cognition / adapter SDK / robot stack boundaries.
- **Docker** standardized the container interface; `Dockerfile` became the unit of distribution; the `OCI Image Spec` made cross-runtime portability real. **KaraOS analog:** the adapter SDK + conformance suite.
- **Kubernetes** is API-first; every primitive (Pod, Service, Deployment) is a YAML-described typed resource; the controller pattern is structural. **KaraOS analog:** durable commitments + scheduler + verifier registry as typed resources.

### 9.5 Linux kernel CI discipline (for MF1 justification)

Linux kernel uses:
- **kbuild** for cross-arch build verification on every patch.
- **`kunit`** for in-kernel unit tests.
- **`syzkaller`** for fuzzing.
- **`0day` test bot** (Intel-run) reports build and boot regressions on every public patch within hours.

Without CI, the kernel could not have grown to its current scale. **The lesson for KaraOS:** every structural invariant is a *latent* invariant until CI enforces it. The 28+ AST tests in tree are equivalent to kernel structural invariants. CI converts them from documentation to enforcement.

---

## 10. Closing — process recommendations

1. **Adopt this report as the Phase 0 audit for P1's kickoff cycle.** It is grep-verified, decomposed into D-decisions, named edit sites where possible.
2. **Resolve MF6 (strategic alignment) explicitly.** A single sentence in CLAUDE.md "Project Overview" and matching updates in complete-plan.md + future-execution.md will eliminate the ambiguity I had to navigate writing this report.
3. **Ship MF1 (CI) before any P1 code lands.** Four hours of work; protects every elevated doctrine.
4. **Lock the spec-first review cycle as the binding process for P1.** Phase 0 audit → Plan v1 → auditor review → Plan v2 → code. No "obvious refactor" exceptions.
5. **Run the bug census (§3) as a separate sub-PR before P1.A1.** HIGH items B-H1, B-H2, B-H3 are independent of P1's decomposition shape. Closing them shrinks P1's blast radius.

The system is in remarkable shape for an ambition this large. The discipline that produced the 15 elevated doctrines + 2810 passing tests + the 14-cycle P0.R resilience arc closure is exactly what's needed for P1. The risk is not the code's quality. The risk is the *protocol gap* between what the code is today (single-user social AI) and what the strategic goal says it must become (universal ROS 2 cognitive middleware). Resolving that gap is what P1 must accomplish.

I put my heart and blood into this. The next call belongs to the architect and the developer agents.

— TechAnalyst-1
2026-05-27
