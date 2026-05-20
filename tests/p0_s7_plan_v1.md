# P0.S7 — Phase 3B (D-A: SHARED CONTEXT block) — Plan v1

**Date:** 2026-05-18
**Author:** architect
**Status:** Plan v1 — drafted against Phase 0 D-lock (2026-05-18) + 2 D-precision items (D3/D4 privacy mechanism clarification + D4.a SQLite version handling) + 3 missed threats (A: disputed-session, B: producer-side audience_ids tagging, C: privacy semantics). Standing by for auditor's Plan v1 review → Plan v2 revision → joint sign-off → developer handoff.

**Phase 0 audit:** `tests/p0_s7_audit.md` (2026-05-18, premise reset + 5-deferral decomposition + D-A first slice).

---

## 1. Locked decision reference (Phase 0 D-lock 2026-05-18)

| ID | Locked at | Rationale |
|---|---|---|
| D1 Sub-PR slicing | D1.a — D-A alone | Schema in place (S107); smallest dependency surface; value-then-refactor sequencing |
| D2 Block contents | D2.a — Last N turns filtered, no LLM synthesis, no per-speaker grouping | ROOM block already covers rich format; SHARED CONTEXT complements with persistent source |
| D3 Retrieval method placement | D3.a — `FaceDB.get_recent_room_conversation(...)` | Mirrors S113 `search_room_turns` pattern; preserves layering |
| D4 Audience filter shape | D4.a — `audience_ids IS NULL OR audience_ids LIKE '%"pid"%'` | Works on all SQLite versions; Plan v2 may revise if Jetson SQLite ≥3.45 verified AND LIKE surfaces a bug |
| D5 Block gating | D5.b — Independent `SHARED_CONTEXT_BLOCK_ENABLED` flag + multi-person gate | Preserves rollback discipline per P0.10 lesson |
| D6 Coexistence | D6.a — Both blocks render in parallel during validation window | D-C cleanup is its own follow-up after canary validates |
| D7 Block format | D7.a — Reuse `_build_cross_person_excerpts` render shape | Keeps brain pattern-recognition surface stable |
| D8 Test coverage | D8.c — Unit + AST + 5-row deliberate-regression Phase 4 | Same P0.S6 induction discipline |
| **P1** (D-precision 1) | Audience-filter privacy semantic = **(ii) best_friend override** | `_visibility_clause` does NOT apply to `conversation_log` (no privacy_level column); audience_ids IS the mechanism; owner sees all room rows regardless of audience tagging (matches S95 3A.4.6 simplified owner-access model) |
| **P2** (D-precision 2) | Lock D4.a for safety; defer json_each evaluation to Plan v2 | Jetson SQLite version unverified at Plan v1 drafting; LIKE-substring safety pinned via explicit collision test ("jagan_001" vs "jagan_0011") |
| **T-A** (Threat A) | Disputed-session caller → skip block entirely (no stub render) | Same shape as S91 CROSS-PERSON PRIVACY block behavior for disputed speakers (don't expose room history to identity-disputed callers) |
| **T-B** (Threat B) | Producer-side audience_ids semantic = **(β) all room participants at turn time** | Single source of truth at write time; `[speaker_pid]` legacy default upgraded for room-scoped turns; backfill rows (audience_ids IS NULL) handled via D4.a OR clause |
| **T-C** (Threat C) | Plan v1 §3 explicitly documents `_visibility_clause` vs `audience_ids` are distinct mechanisms | Read-side documentation; no code mechanism change |

---

## 2. Architectural overview

Three-layer surface change (producer → storage → consumer):

```
┌─────────────────────────────────────────────────────────────────────┐
│  PRODUCER (T-B Phase 1)                                              │
│  log_turn callers in pipeline.py upgrade audience_ids from           │
│  [speaker_pid]  →  list(_active_room_participants_at_turn_time)      │
│  Single-person sessions: no behavioral change (set is {pid}).        │
│  Multi-person sessions: all room participants tagged as audience.    │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STORAGE (already-shipped S107 + S111 schema)                        │
│  conversation_log.room_session_id  +  audience_ids JSON  +           │
│  addressed_to  +  idx_conv_log_room(room_session_id, ts DESC)        │
│  No schema change required for D-A.                                  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  CONSUMER (D-A Phase 1 + Phase 2)                                    │
│  FaceDB.get_recent_room_conversation(                                │
│    room_session_id, requester_pid, best_friend_id,                   │
│    limit=10, since_ts=None                                           │
│  ) → list[dict]                                                      │
│                                                                       │
│  WHERE room_session_id = ?                                           │
│    AND (                                                             │
│      ? IS NOT NULL AND ? = ?                       -- best_friend    │
│      OR audience_ids IS NULL                       -- legacy rows    │
│      OR audience_ids LIKE '%"' || ? || '"%'        -- normal rows    │
│    )                                                                 │
│  ORDER BY ts ASC                                                     │
│  LIMIT ?                                                             │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PROMPT INJECTION (D-A Phase 2)                                      │
│  _build_shared_context_block(                                        │
│    room_session_id, requester_pid, best_friend_id, db,               │
│    disputed_check_fn                                                  │
│  ) → str | None                                                       │
│                                                                       │
│  Gates: SHARED_CONTEXT_BLOCK_ENABLED flag (D5.b)                     │
│       + multi-person room (len(active_sessions) >= 2)                 │
│       + NOT _is_disputed(requester_pid) (T-A)                        │
│                                                                       │
│  Render: same line shape as _build_cross_person_excerpts (D7.a)      │
│  Injection: appended to _build_system_prompt after <<<ROOM>>>        │
└─────────────────────────────────────────────────────────────────────┘
```

The block is purely **additive** — `<<<ROOM>>>` block (in-memory current-session turns) continues to render unchanged; `<<<SHARED CONTEXT>>>` adds the persistent-DB-backed complement for cross-session room history. `_build_cross_person_excerpts` continues to render during the validation window (D-C cleanup is its own follow-up).

---

## 3. Privacy mechanism — `_visibility_clause` vs `audience_ids` (T-C)

**Read-side documentation. No code mechanism change in D-A.**

These are two distinct privacy mechanisms operating on two different tables:

| Mechanism | Table | Owner column | Reader filter |
|---|---|---|---|
| `_visibility_clause` (brain_agent.py) | `knowledge` | `privacy_level` (4-tier: public / personal / household / system_only) | Composed AND predicate into SELECT |
| `audience_ids` (D-A) | `conversation_log` | `audience_ids` (JSON array of pids) | LIKE-substring + best_friend-override OR clause |

**Why two mechanisms instead of one:**

The `knowledge` table holds extracted facts (e.g., `Lexi.lives_in='Hyderabad'`); privacy tiering is per-attribute and slot-driven (S95 P3.2 LLM classifier or static-map). The `conversation_log` holds raw turn transcripts; privacy is per-turn and intent-driven (who was actually IN the room when the turn was uttered). Unifying them would force every turn into a tier-classification path (extra LLM call per log_turn) or every fact into an audience-list (over-restrictive for facts that the speaker explicitly shared with the household).

**The mechanisms are complementary, not interchangeable.** `_visibility_clause` does NOT apply to `conversation_log` retrieval and never will under D-A's scope.

Plan v1 captures this for future readers so post-D-A refactor work doesn't conflate the two mechanisms.

---

## 4. Producer-side audience_ids upgrade (T-B Phase 1)

### 4.1 Current state (per S107 + S112 audit)

Two `log_turn` callers in pipeline.py:
- `conversation_turn` at pipeline.py (around the existing `db.log_turn(person_id, "user", text, ...)` site) — passes `audience_ids=[pid]`
- `_kairos_tick` (same shape) — passes `audience_ids=[pid]`

Plus the assistant-turn append within conversation_turn that mirrors the same audience_ids semantic.

### 4.2 Plan v1 lock (T-B option β)

Both callers compute audience_ids from the current room participants:

```python
# Single source of truth at write time.
_room_audience: list[str] = sorted(_pipeline_state_store.peek_active_room_participants())
# Single-person session: list is [speaker_pid] (no behavioral change).
# Multi-person session: list is all participants at turn time.
if not _room_audience:
    # Defensive: room state may have been cleared mid-turn (race vs _close_session).
    # Fall back to speaker-only audience to preserve back-compat.
    _room_audience = [person_id]

db.log_turn(
    person_id,
    role,
    text,
    room_session_id=_current_room_session,
    audience_ids=_room_audience,
    addressed_to=...  # unchanged from S111
)
```

**Why `sorted()`:** deterministic ordering for the JSON-encoded audience_ids string. Without sorting, two semantically-equal turns could differ by audience_ids string permutation (test flakiness + cache key drift).

**Why the defensive `if not _room_audience:` branch:** the room state could theoretically be empty during a tight race between `conversation_turn` and `_close_session`. The defensive branch preserves the S107 backfill semantic so D-A's retrieval contract doesn't break on the edge case.

### 4.3 Non-claim: existing rows unchanged

Pre-T-B rows in `conversation_log` keep their existing audience_ids values (either `NULL` from legacy backfill, or `[speaker_pid]` from S107-onward writes). D-A's retrieval handles both via the `audience_ids IS NULL OR audience_ids LIKE '%"pid"%'` OR clause — backwards compatible.

**No data migration in D-A.** A future sub-PR could backfill historical multi-person rows with the full participant list IF the value justifies it; D-A intentionally avoids the data-archaeology problem.

---

## 5. `FaceDB.get_recent_room_conversation` — full spec

### 5.1 Signature

```python
def get_recent_room_conversation(
    self,
    room_session_id: str,
    requester_pid: str,
    best_friend_id: "str | None",
    limit: int = 10,
    since_ts: "float | None" = None,
) -> "list[dict]":
    """Return the last ``limit`` turns from ``conversation_log`` scoped
    to ``room_session_id``, filtered by audience visibility (T-B option
    β) with best_friend owner override (P1 option ii).

    Each row: ``{person_id, role, text, ts, audience_ids, addressed_to}``.
    Rows ordered ascending by ``ts`` (chronological — matches the brain's
    expected reading order).

    Args:
      room_session_id:   The current room context. NULL/empty → returns [].
      requester_pid:     The speaker the block is being rendered for.
      best_friend_id:    The current best_friend pid (from FaceDB.get_best_friend()).
                          If requester_pid == best_friend_id, owner override fires
                          and audience_ids filter is bypassed.
      limit:             Max turns returned (default 10).
      since_ts:          If provided, only turns with ts >= since_ts returned
                          (used by Plan v1 §6 to dedupe in-memory + DB overlap).

    Returns: list of dicts. Empty list if room_session_id is empty/None,
             or no rows match the audience filter, or DB error (logged).
    """
```

### 5.2 SQL shape (locked Plan v1)

```sql
SELECT person_id, role, text, ts, audience_ids, addressed_to
FROM conversation_log
WHERE room_session_id = :room_session_id
  AND (
    -- Owner override (P1 option ii)
    (:best_friend_id IS NOT NULL AND :requester_pid = :best_friend_id)
    OR
    -- Legacy backfill rows (audience_ids NULL = visible per legacy semantic)
    audience_ids IS NULL
    OR
    -- Audience-includes-requester (T-B option β consumer side)
    audience_ids LIKE '%"' || :requester_pid || '"%'
  )
  AND (:since_ts IS NULL OR ts >= :since_ts)
ORDER BY ts ASC
LIMIT :limit;
```

Uses `idx_conv_log_room(room_session_id, ts DESC)` for the primary lookup; the audience OR clause is a row-level post-filter. Expected sub-10ms on Jetson for limit=10.

### 5.3 Empty-result-graceful

The method returns `[]` (not raises) when:
- `room_session_id` is None or empty string (defensive guard at function top)
- No conversation_log rows match the filters
- SQLite OperationalError (logged via `print(f"[FaceDB] get_recent_room_conversation error: {e!r}")`, returns `[]`)

Same defensive shape as `search_room_turns` (S113).

### 5.4 Non-claim: no `addressed_to` filter

D-A does NOT filter by `addressed_to`. The block surfaces ALL audience-visible turns in the room, regardless of who they were directly addressed to. Rationale: the brain reads `[addressing:X]` markers (S113) to determine address direction itself; the retrieval shouldn't pre-filter that signal away.

---

## 6. `_build_shared_context_block` — full spec

### 6.1 Signature

```python
def _build_shared_context_block(
    room_session_id: "str | None",
    requester_pid: str,
    best_friend_id: "str | None",
    db: "FaceDB",
    is_disputed_fn: "Callable[[str], bool]",
    active_session_count: int,
    limit: int = 10,
    now: "float | None" = None,
    since_ts: "float | None" = None,
) -> "str | None":
    """Phase 3B D-A — render <<<SHARED CONTEXT>>> block from persistent
    conversation_log filtered by room_session_id + audience + best_friend
    override (Plan v1 §5).

    Returns None when:
      - SHARED_CONTEXT_BLOCK_ENABLED is False
      - active_session_count < 2 (single-person room, ROOM block already gates)
      - is_disputed_fn(requester_pid) returns True (T-A disputed-session skip)
      - room_session_id is None / empty
      - get_recent_room_conversation returns []
    """
```

### 6.2 Gating order (locked Plan v1)

```python
if not SHARED_CONTEXT_BLOCK_ENABLED:
    return None
if active_session_count < 2:
    return None
if not room_session_id:
    return None
if is_disputed_fn(requester_pid):
    # T-A: identity-disputed speaker should NOT see room history.
    # Same shape as S91 CROSS-PERSON PRIVACY block behavior.
    return None
```

Each gate's purpose:
1. **Flag gate** — rollback discipline (D5.b).
2. **Multi-person gate** — block redundant with ROOM block's single-person omission; cheaper to short-circuit.
3. **room_session_id presence** — defensive against the same race as §4.2.
4. **Disputed-session skip** — T-A guard; defense against identity-disputed callers retrieving room history they shouldn't trust.

### 6.3 Block render shape (D7.a — reuse `_build_cross_person_excerpts` shape)

```
<<<SHARED CONTEXT>>>
The following turns were spoken in this room (from persistent memory):
[5m ago] Lexi: "I've been feeling anxious about my thesis"
[3m ago] you [to Lexi]: "What's the deadline?"
[2m ago] Lexi: "Friday at noon"
<<<END SHARED CONTEXT>>>
```

- Per-line format: `[{age_str}] {speaker_name_or_you}{addressee_suffix}: "{text}"`.
- `age_str` uses the same "just now" (< 60s) / "Nm ago" (< 1h) / "Nh ago" formatter as `_build_cross_person_excerpts` (S111 HIGH).
- `you [to X]` form when `role == "assistant"` AND `addressed_to` is set + resolvable to a session-canonical name (S113).
- Default speaker_name resolution: prefer session-canonical name if speaker is active, else fall back to `_session_store.peek_snapshot(pid).person_name`, else fall back to pid prefix.

### 6.4 Prompt injection placement

Inserted in `_build_system_prompt` between the existing `<<<ROOM>>>` block injection point and the `<<<EMOTIONAL CONTEXT>>>` block. Order: ROOM (in-memory now) → SHARED CONTEXT (persistent room history) → EMOTIONAL CONTEXT → other blocks.

**Rationale for ordering:** brain reads top-down; ROOM is most-immediate, SHARED CONTEXT is the persistent complement, EMOTIONAL CONTEXT comes after both since emotion is per-speaker not per-turn.

### 6.5 Dedup against `<<<ROOM>>>` (threat §6.2 mitigation)

The ROOM block renders in-memory turns from `_conversation_store._history` for the CURRENT session. SHARED CONTEXT renders persistent turns from `conversation_log` scoped to the room_session_id.

**Overlap problem:** if the current session has been running long enough that turns have been written to `conversation_log` AND are still in `_conversation_store._history`, both blocks render the same content.

**Plan v1 mitigation:** `since_ts` param on `_build_shared_context_block` and `get_recent_room_conversation`. Caller computes `since_ts = _pipeline_state_store.peek_active_room_started_at()` — SHARED CONTEXT only returns turns from BEFORE the current room session started. Two cases:

- **Fresh room (just minted, no prior turns):** `since_ts` filter returns 0 rows → block returns None → no render.
- **Returning user (room was previously active, ended, now re-minted):** previous room's turns have different room_session_id → already excluded by the `room_session_id = ?` filter.

**Edge case:** the current room session may have its own historical turns (e.g., user closed system mid-session and re-booted — pipeline reconciles the room_session_id mint logic). For D-A scope, treat this as "if room_session_id is the same and turns exist in conversation_log, they're shareable." Plan v2 can revise if canary surfaces conflict.

### 6.6 Call sites

Two call sites in pipeline.py mirror the `_build_room_block` placement:
- `conversation_turn` vision_state build (pipeline.py:3123 area) — block fires for the current speaker's prompt
- `_kairos_tick` vision_state build (pipeline.py:7776 area) — block fires for the KAIROS-selected speaker's prompt

Both call sites compute the same args; pull from `_pipeline_state_store.peek_active_room_session()` + `peek_active_room_started_at()` + `len(_active_sessions)`.

---

## 7. Config additions

`core/config.py`:

```python
# P0.S7 D-A — SHARED CONTEXT block (Phase 3B retrieval-side wiring)
SHARED_CONTEXT_BLOCK_ENABLED: bool = True
SHARED_CONTEXT_BLOCK_TURN_CAP: int = 10
```

Mirrors the ROOM_BLOCK_ENABLED + ROOM_BLOCK_TURN_CAP shape (S113 P3B.1).

---

## 8. Test specification (D8.c)

### Phase 1 tests (FaceDB.get_recent_room_conversation + producer upgrade)

1. **`test_get_recent_room_conversation_returns_audience_visible_rows`** — seed 3 turns in `conversation_log` with mixed audience_ids `[a]`, `[a, b]`, `[b]`; query as requester `a`; assert returns first 2 rows ordered by ts.
2. **`test_get_recent_room_conversation_legacy_null_audience_visible`** — seed 1 turn with `audience_ids=NULL`; query as requester `a`; assert returns the row (legacy backfill compatibility).
3. **`test_get_recent_room_conversation_best_friend_owner_override`** — seed turn with `audience_ids=[c]`; query as requester `a` with `best_friend_id=a`; assert returns the row (owner override per P1 ii).
4. **`test_get_recent_room_conversation_room_session_id_filter`** — seed 2 turns under different room_session_id values; query for room R1; assert only R1 rows return (no cross-room leak).
5. **`test_get_recent_room_conversation_pid_collision_rejection`** — seed turn with `audience_ids=["jagan_0011"]`; query as requester `jagan_001`; assert returns 0 rows (P2 LIKE-substring safety — quote boundary prevents collision).
6. **`test_get_recent_room_conversation_since_ts_filter`** — seed 3 turns at ts=100, 200, 300; query with `since_ts=150`; assert returns only ts=200, 300 (dedup-with-ROOM-block contract).
7. **`test_get_recent_room_conversation_empty_room_session_id_graceful`** — query with `room_session_id=None`; assert returns `[]` (no exception).
8. **`test_log_turn_writes_full_room_audience`** — open 3 sessions, call `db.log_turn` from pipeline.py path (NOT directly — exercises producer-side upgrade); assert `audience_ids` in DB is the full participant list (sorted), not `[speaker_pid]`.

### Phase 2 tests (`_build_shared_context_block` + pipeline integration)

9. **`test_shared_context_block_renders_multi_person`** — mock `FaceDB.get_recent_room_conversation` to return 2 turns; assert block contains the markers + 2 lines + correct format.
10. **`test_shared_context_block_single_person_returns_none`** — `active_session_count=1`; assert returns None.
11. **`test_shared_context_block_flag_off_returns_none`** — monkeypatch `SHARED_CONTEXT_BLOCK_ENABLED=False`; assert returns None.
12. **`test_shared_context_block_disputed_caller_returns_none`** — T-A: `is_disputed_fn` returns True; assert returns None (no SQL call made — disputed gate fires before DB fetch).
13. **`test_shared_context_block_injected_in_build_system_prompt`** — source-inspection test asserting `_build_system_prompt` calls `_build_shared_context_block` AND that the call site is between ROOM block injection and EMOTIONAL CONTEXT injection (Plan v1 §6.4 ordering).

### Phase 3 tests (AST source-inspection invariants)

14. **`test_log_turn_callers_use_room_participants_for_audience`** — AST scan pipeline.py for `db.log_turn(` calls; assert each call site passes `audience_ids=_room_audience` (or equivalent — the locked Plan v1 §4.2 shape), NOT `audience_ids=[pid]`.
15. **`test_shared_context_block_disputed_guard_present`** — AST scan `_build_shared_context_block` body asserts `is_disputed_fn(requester_pid)` is called BEFORE any DB call (`db.get_recent_room_conversation`).
16. **`test_facedb_get_recent_room_conversation_signature`** — AST scan FaceDB class; assert the method has the signature locked in Plan v1 §5.1 (all 5 kwargs present, best_friend_id type Optional[str], since_ts type Optional[float]).

### Phase 4 (deliberate-regression confirmations, closure-report items NOT pytest)

Confirmed by injecting each violation, running the test, observing the correct failure, then reverting:

- **(a)** Inject `audience_ids=[pid]` in one log_turn caller → Phase 3 test 14 fails with violation message.
- **(b)** Inject `db.get_recent_room_conversation(...)` call BEFORE `is_disputed_fn(...)` check → Phase 3 test 15 fails with ordering message.
- **(c)** Inject pid-collision row (`audience_ids=["jagan_0011"]`) in seed; query as `jagan_001` → Phase 1 test 5 fails (regression guard against LIKE-substring boundary loss).
- **(d)** Drop the `room_session_id = ?` clause from the SQL → Phase 1 test 4 fails (cross-room leak).
- **(e)** Drop the `best_friend_id = requester_pid` owner-override clause → Phase 1 test 3 fails (owner can't see audience-restricted rows).

**Total Phase 1+2+3 tests: 16.** Suite delta forecast: **2310 → 2326** (+16).

This is 4 above the Phase 0 audit estimate (+10-12). Increase rationale: T-B producer-side upgrade added 1 test (8); T-A disputed-guard added 1 test (12) + 1 AST check (15); P2 collision-safety added 1 test (5); since_ts dedup added 1 test (6). All four are direct consequences of the auditor's locked precision items / threats.

---

## 9. Implementation phases (locked)

### Phase 1 — Storage layer + producer upgrade (+8 tests)

- New method `FaceDB.get_recent_room_conversation` (Plan v1 §5)
- Producer-side audience_ids upgrade in 2 `log_turn` callers (Plan v1 §4)
- Tests 1-8 from §8 above
- **Suite checkpoint:** 2310 → 2318 (+8)

### Phase 2 — Consumer + prompt integration (+5 tests)

- New helper `_build_shared_context_block` (Plan v1 §6)
- 2 call sites: `conversation_turn` + `_kairos_tick` (Plan v1 §6.6)
- `_build_system_prompt` injection between ROOM and EMOTIONAL CONTEXT blocks (Plan v1 §6.4)
- 2 config additions: `SHARED_CONTEXT_BLOCK_ENABLED`, `SHARED_CONTEXT_BLOCK_TURN_CAP` (Plan v1 §7)
- Tests 9-13 from §8 above
- **Suite checkpoint:** 2318 → 2323 (+5)

### Phase 3 — Structural invariants (+3 tests)

- 3 AST source-inspection tests (Plan v1 §8 tests 14-16)
- **Suite checkpoint:** 2323 → 2326 (+3)

### Phase 4 — Deliberate-regression confirmations + closure (+0 tests)

- 5 deliberate-regression confirmations per Plan v1 §8 Phase 4 list
- Closure-report banking:
  - Sub-pattern A 4th instance memory-note (still NOT elevated to CLAUDE.md doctrine — 5+ threshold)
  - Spec-first review cycle 8-for-8 → 9-for-9
  - T-A / T-B / T-C threats resolved with explicit non-claim documentation
  - D-precision items 1 + 2 resolution table

---

## 10. Latency budget (audit §6.1)

D-A adds one SQL query per multi-person turn. Expected on Jetson:
- Index `idx_conv_log_room(room_session_id, ts DESC)` lookup: ~1ms
- Row-level audience filter (LIKE-substring): ~0.1ms per matched row × ~10 rows = ~1ms
- JSON parse client-side: ~0.5ms

**Target: < 10ms p99 for limit=10.** Phase 1 test 1 includes a latency assertion (`assert elapsed_ms < 50`) — generous to allow CI overhead; production target is tighter.

If real production latency exceeds 50ms, Plan v2 may revise to:
- Cache the prior turn's result keyed on (room_session_id, requester_pid, last_room_ts)
- Move to json_each/json_extract if Jetson SQLite ≥3.45 confirmed (D4.b path)

---

## 11. Token-budget impact (audit §6.3)

Both `_build_cross_person_excerpts` AND `<<<SHARED CONTEXT>>>` render during the validation window (D6.a). Token-budget estimate:

- `_build_cross_person_excerpts` (current): ~6 turns × ~30 tokens/turn = ~180 tokens per multi-person turn
- `<<<SHARED CONTEXT>>>` (D-A): up to 10 turns × ~30 tokens/turn = ~300 tokens per multi-person turn
- Overlap (same source-text) after `since_ts` dedup (Plan v1 §6.5): expected 0 tokens overlap

**Worst-case combined: ~480 tokens per multi-person turn during validation window.** Roughly +2% of an 18k-token prompt. Tolerable.

After D-C cleanup (`_build_cross_person_excerpts` deletion) lands as a follow-up, the budget drops back to ~300 tokens.

---

## 12. Validation gate (closure criteria)

1. **All 16 new tests green** + full-suite green at 2326.
2. **5/5 deliberate-regression confirmations** pass (induction protocol).
3. **Latency p99 < 50ms** verified in Phase 1 test 1.
4. **3 missed threats from Phase 0 audit (T-A / T-B / T-C) resolved** with explicit non-claim documentation in closure report.
5. **D-precision items 1 + 2 resolution** documented in closure report.

---

## 13. Discipline-count predictions (unchanged from audit §5)

- Spec-first review cycle: **8-for-8 → 9-for-9** on closure
- Sub-pattern A: 3rd → **4th instance** banked as memory-note (still NOT elevated to standalone `###` doctrine; 5+ threshold)
- Tripwires-must-match-deferral-surface: stays **4-for-4** (no tripwire-guarded deferral introduced)
- Developer-improves-on-spec: stays **6-for-6** unless code phase surfaces a mechanism improvement
- Induction-surfaces-invariant-gaps: stays **7-for-7** unless Phase 4 surfaces a real gap

---

## 14. Open items / risks

1. **Jetson SQLite version unverified.** Plan v1 locks D4.a (LIKE-substring) for safety. Plan v2 will verify the version empirically (`sqlite3 -version` on the Jetson dev unit) and decide whether to keep D4.a or revise to json_each / json_extract.
2. **`_active_room_participants` race during turn-flight.** Defensive fallback to `[person_id]` in Plan v1 §4.2 covers the race. Phase 4 deliberate-regression doesn't need to exercise this directly; the fallback is unconditional.
3. **D-C cleanup not gated on D-A closure.** D-A and D-C are independent. D-A closure DOES NOT trigger D-C automatically — D-C still requires the live multi-person canary that hasn't run.
4. **Backfill-row visibility semantics.** Audience-NULL legacy rows are visible to ALL room members (S107 backfill default). D-A's OR clause preserves this. If a future privacy review wants tighter semantics on legacy rows, a one-shot backfill migration is the path forward.
5. **D-A retrieval contract does NOT account for room continuity across system reboots.** If room_session_id is re-minted across boots, old room's turns are scoped out by the `room_session_id = ?` filter. Plan v2 may add a "same participants within N minutes" union if Jagan reports cross-boot continuity is a UX issue.

---

## 15. Reference documents

- `tests/p0_s7_audit.md` — Phase 0 audit (premise reset; 5-deferral decomposition; D-A first slice)
- `everything_about_system.md` §145 (Q3 History Architecture Redesign), §163 (Room session lifecycle), §163.3 (RoomOrchestrator class non-goal)
- `CLAUDE.md` — Sessions 107 (schema), 111 (addressed_to), 112 (room lifecycle), 113 (3B.1-3B.6 features)
- `core/db.py:1278` — existing `search_room_turns` (S113) — reference shape for `get_recent_room_conversation`
- `core/faces_db_migrations.py:173-204` (v=7 room schema), `:217-250` (v=9 backfill)
- `pipeline.py:1166` (`_build_cross_person_excerpts` — D7.a render-shape source), `:1288` (`_build_room_block` — placement reference), `:5216` (D-C future cleanup target)
- `tests/p0_s6_plan_v2.md` — reference Plan v1→v2 shape
- `tests/p0_s1_audit.md` + `tests/p0_s1_plan_v2.md` — reference 4-phase implementation shape
