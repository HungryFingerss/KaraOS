# P0.S7 — Phase 3B (D-A: SHARED CONTEXT block) — Plan v2

**Date:** 2026-05-18
**Author:** architect
**Status:** Plan v2 — drafted against locked D1-D8 + auditor's 6 precision items from Plan v1 review (2 CRITICAL + 1 MEDIUM-3 + 1 MEDIUM-4 + 2 LOW). Plan v1 retained at `tests/p0_s7_plan_v1.md` for delta visibility. Standing by for auditor's Plan v2 review → joint sign-off → developer handoff.

**Phase 0 audit:** `tests/p0_s7_audit.md`.

**Delta from Plan v1 (6 precision items):**
- **CRITICAL 1** — D4.a LIKE pattern's `_` wildcard collision (UNSAFE; every pid contains `_`). Plan v2 locks option (a): Python-side escape via `_escape_like_pid()` helper + SQL `ESCAPE '\\'` clause. New Phase 1 test for underscore-wildcard rejection.
- **CRITICAL 2** — `since_ts` dedup as designed is a no-op. Plan v2 locks option (a): drop `since_ts` entirely. Remove from method signature + helper signature + caller. Drop Plan v1 test 6. Accept validation-window overlap per Plan v1 §11 token-budget acceptance; D-C cleanup is the structural fix.
- **MEDIUM 3** — Exhaustive log_turn call-site enumeration. Plan v2 §4.1 commits to all 5 sites (grep-verified): 2 in `_kairos_tick` (user "[silence]" + assistant response), 3 in `conversation_turn` (S113 user-to-user silence path + normal user + normal assistant).
- **MEDIUM 4** — Defensive audience_ids fallback extended for speaker-missing case. Invariant: speaker is ALWAYS in their own audience list.
- **LOW 5** — Test 8 split into (8a) unit test on extracted `_compute_room_audience(participants, person_id)` helper + (8b) behavioral DB-persistence test. Helper extraction is structural improvement.
- **LOW 6** — Latency assertion uses median-of-10 measurement for flake resistance.

**Test count revised:** 16 → **17** (+1 underscore wildcard, -1 since_ts drop, +1 test 8 split). Suite delta: **2310 → 2327**.

Locked D-decisions and Plan v1 contract clauses unchanged except where explicit revision noted below.

---

## 1. Locked decision reference (unchanged from Plan v1 except where Plan v2 deltas note)

| ID | Locked at | Plan v2 delta |
|---|---|---|
| D1 Sub-PR slicing | D1.a — D-A alone | — |
| D2 Block contents | D2.a — Last N turns filtered, no LLM synthesis | — |
| D3 Retrieval method placement | D3.a — `FaceDB.get_recent_room_conversation(...)` | Signature trimmed (since_ts removed per CRITICAL 2) |
| D4 Audience filter shape | D4.a — Python-escape + `LIKE '%"' \|\| ? \|\| '"%' ESCAPE '\\'` | **CRITICAL 1 — escape revision; see §2** |
| D5 Block gating | D5.b — Independent flag + multi-person gate | — |
| D6 Coexistence | D6.a — Both blocks render in parallel | — |
| D7 Block format | D7.a — Reuse `_build_cross_person_excerpts` shape | — |
| D8 Test coverage | D8.c — Unit + AST + 5-row deliberate-regression | Test count 16 → 17 |
| **P1** Audience-filter privacy semantic | (ii) best_friend override | — |
| **P2** D4.a SQLite version handling | Locked D4.a; defer json_each to Plan v3 | — |
| **T-A** Disputed-session interaction | Skip block entirely on disputed caller | — |
| **T-B** Producer-side audience_ids semantic | (β) all room participants at turn time | **MEDIUM 3 + MEDIUM 4 + LOW 5 revisions; see §4** |
| **T-C** Privacy semantics clarification | Read-side doc; no mechanism change | — |
| **CRITICAL 1** (Plan v2) | Python-side escape of `_` + `%` + `\\` in pid | New |
| **CRITICAL 2** (Plan v2) | Drop `since_ts` parameter entirely | New |

---

## 2. CRITICAL 1 — LIKE wildcard `_` escape (locked Plan v2)

**Root cause:** SQLite LIKE syntax treats `_` as a single-character wildcard. The Plan v1 pattern `LIKE '%"' || :requester_pid || '"%'` with `:requester_pid = "jagan_001"` produces the LIKE pattern `%"jagan_001"%`. The `_` characters match ANY single character — so this pattern matches `"jaganX001"`, `"jaganA001"`, `"jagan/001"`, etc. Every pid in this codebase contains `_` (jagan_001, stranger_a0d44122, kara_friend_xyz, etc.), so the wildcard collision risk is UNIVERSAL, not edge-case.

**Plan v2 fix — Python-side escape + ESCAPE clause:**

```python
def _escape_like_pid(pid: str) -> str:
    """P0.S7 CRITICAL 1 — escape pid for safe substring use in a SQLite LIKE
    pattern.

    SQLite LIKE treats `_` as single-character wildcard and `%` as multi-char
    wildcard. Every pid in this codebase contains `_` (e.g. jagan_001), so the
    naked pid in a LIKE pattern collides with any string of the same length
    sharing the surrounding context.

    Escape order:
      1. Backslash first (otherwise step 2 + 3 produce double-escaped sequences)
      2. Underscore  → \\_
      3. Percent     → \\%

    The query uses the ESCAPE '\\' clause to recognize the escape character.
    """
    return (
        pid
        .replace("\\", "\\\\")
        .replace("_", "\\_")
        .replace("%", "\\%")
    )
```

**SQL change:**

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
    -- :escaped_pid is the result of _escape_like_pid(requester_pid)
    audience_ids LIKE '%"' || :escaped_pid || '"%' ESCAPE '\'
  )
ORDER BY ts ASC
LIMIT :limit;
```

**Bind parameter shape:**

```python
escaped_pid = _escape_like_pid(requester_pid)
cursor.execute(
    SQL,
    {
        "room_session_id": room_session_id,
        "best_friend_id":  best_friend_id,
        "requester_pid":   requester_pid,      # for owner-override equality check
        "escaped_pid":     escaped_pid,         # for LIKE-substring check
        "limit":           limit,
    },
)
```

Two distinct binds for the same conceptual pid: the equality clause needs the raw pid, the LIKE clause needs the escaped form.

**Compatibility:** ESCAPE clause works on ALL SQLite versions back to 3.0.0. No version dependency.

**New test (replaces / extends Plan v1 test 5):**

- **test_get_recent_room_conversation_pid_collision_rejection** (Plan v1) — verifies the quote-boundary catches suffix collision (`jagan_001` vs `jagan_0011`). Kept.
- **test_get_recent_room_conversation_underscore_wildcard_rejection** (Plan v2 NEW) — seed `audience_ids=["jaganX001"]` where X is `A`, `Z`, `/`, and `*` (4 sub-cases via parametrize); query as `jagan_001`; assert 0 rows for each X. Without the ESCAPE clause this test fails (the `_` wildcard matches X); with the ESCAPE clause it passes.

---

## 3. CRITICAL 2 — `since_ts` dropped entirely (locked Plan v2)

**Root cause:** Plan v1 §6.5 claimed `since_ts = peek_active_room_started_at()` would scope SHARED CONTEXT to "older than current room session started." But the SQL was `ts >= :since_ts` which returns CURRENT-session turns (opposite direction). And inverting to `ts < :since_ts` returns empty by construction since `room_session_id = current_room` implies continuous session per S112 design — no turn with same room_id has ts before room_start.

The `since_ts` parameter as designed is a no-op in the only case where it would actually run.

**Plan v2 fix — drop `since_ts` entirely:**

```python
# Plan v2 method signature (since_ts removed)
def get_recent_room_conversation(
    self,
    room_session_id: str,
    requester_pid: str,
    best_friend_id: "str | None",
    limit: int = 10,
) -> "list[dict]":
    ...
```

```python
# Plan v2 helper signature (since_ts removed)
def _build_shared_context_block(
    room_session_id: "str | None",
    requester_pid: str,
    best_friend_id: "str | None",
    db: "FaceDB",
    is_disputed_fn: "Callable[[str], bool]",
    active_session_count: int,
    limit: int = 10,
    now: "float | None" = None,
) -> "str | None":
    ...
```

**Plan v1 test 6 removed:** `test_get_recent_room_conversation_since_ts_filter` — no longer applicable.

**Token-budget impact:** the validation-window overlap between `_build_cross_person_excerpts` and `<<<SHARED CONTEXT>>>` is accepted per Plan v1 §11 (`+300 tokens worst-case` ≈ +2% of an 18k-token prompt). D-C cleanup (delete `_build_cross_person_excerpts`) is the structural fix; it lands as a separate canary-gated follow-up.

**Long-running-session marginal-case acceptance:** if the in-memory `_conversation_store._history` has trimmed to `CONVERSATION_HISTORY_LIMIT=100` while `conversation_log` retains all turns, SHARED CONTEXT may render turns that ROOM block also rendered earlier in the session. Brain treats this as "consistent context with reinforcement" rather than confusion. If real production shows brain-side confusion from this overlap, Plan v3 can revisit real dedup (auditor's CRITICAL 2 option b).

---

## 4. T-B + MEDIUM 3 + MEDIUM 4 + LOW 5 — Producer-side audience_ids (locked Plan v2)

### 4.1 Exhaustive log_turn call-site enumeration (MEDIUM 3, grep-verified 2026-05-18)

Plan v1 §4.1 said "2 functions + 1 assistant append." The grep-verified count is **5 sites total** in `pipeline.py`:

| Site | Line (approx) | Function | Role | Plan v1 audience_ids | Plan v2 audience_ids |
|---|---|---|---|---|---|
| 1 | 3205 | `_kairos_tick` | "user" / "[silence]" | `[person_id]` | `_compute_room_audience(participants, person_id)` |
| 2 | 3208 | `_kairos_tick` | "assistant" / response | `[person_id]` | `_compute_room_audience(participants, person_id)` |
| 3 | 5103 | `conversation_turn` user-to-user silence path (S113 P3B.2) | "user" / text | `[person_id]` | `_compute_room_audience(participants, person_id)` |
| 4 | 5996 | `conversation_turn` | "user" / text | `[person_id]` | `_compute_room_audience(participants, person_id)` |
| 5 | 5998 | `conversation_turn` | "assistant" / response | `[person_id]` | `_compute_room_audience(participants, person_id)` |

**Out-of-scope (grep-verified zero callers):** `core/brain_agent.py:6415` is a docstring reference to `db.log_turn()` (not a call); `test_pipeline.py` / `tests/test_event_log_producer_coverage.py` / `tests/test_concurrent_db_access.py` are test code (Plan v1 §scope: runtime only). No `log_turn` calls in `core/audio.py`, `core/brain.py`, `enroll.py`, or other production modules.

Phase 3 AST test 14 grep-enumerates these 5 sites + asserts each uses `_compute_room_audience(...)` rather than `[person_id]` — single source of truth at the AST layer.

### 4.2 `_compute_room_audience` helper (LOW 5 — extraction)

Extracted as a named module-level helper in `pipeline.py`:

```python
def _compute_room_audience(
    participants: "set[str] | list[str] | tuple[str, ...]",
    person_id: str,
) -> "list[str]":
    """P0.S7 T-B + MEDIUM 4 — compute the audience_ids list for a log_turn
    call.

    Invariant: the speaker (``person_id``) is ALWAYS present in the returned
    audience list. This invariant matters for the D-A retrieval contract:
    `get_recent_room_conversation`'s audience filter checks
    `audience_ids LIKE '%"requester"%'`, which fails for the requester's own
    turn if they're somehow not in the audience list.

    Three cases:
      (a) participants empty (race vs _close_session) → [person_id]
      (b) participants non-empty AND person_id present → sorted(participants)
      (c) participants non-empty AND person_id absent (race vs _open_session) →
          sorted(participants ∪ {person_id})

    sorted() guarantees deterministic JSON-encoded audience_ids string —
    semantically-equal turns serialize to byte-identical strings.
    """
    if not participants:
        # Case (a): empty participants set — defensive fallback to speaker-only.
        return [person_id]
    audience_set: "set[str]" = set(participants)
    if person_id not in audience_set:
        # Case (c): speaker missing from participants — race against
        # _open_session not yet committing the participant. Union the speaker in.
        audience_set.add(person_id)
    # Case (b) AND (c): deterministic ordering.
    return sorted(audience_set)
```

**MEDIUM 4 invariant in code:** the speaker is ALWAYS in the returned list. The function unconditionally ensures this via case (c)'s union.

### 4.3 Updated log_turn call shape (all 5 sites)

```python
# In _kairos_tick (sites 1+2):
_k_audience = _compute_room_audience(
    _pipeline_state_store.peek_active_room_participants(),
    person_id,
)
db.log_turn(person_id, "user", "[silence]",
            room_session_id=_k_room_sid,
            audience_ids=_k_audience)
db.log_turn(person_id, "assistant", response,
            room_session_id=_k_room_sid,
            audience_ids=_k_audience)

# In conversation_turn user-to-user (site 3):
_u2u_audience = _compute_room_audience(
    _pipeline_state_store.peek_active_room_participants(),
    person_id,
)
db.log_turn(person_id, "user", text,
            room_session_id=_room_sid_u2u,
            audience_ids=_u2u_audience)

# In conversation_turn normal turn (sites 4+5):
_ct_audience = _compute_room_audience(
    _pipeline_state_store.peek_active_room_participants(),
    person_id,
)
db.log_turn(person_id, "user", text,
            room_session_id=_room_sid,
            audience_ids=_ct_audience)
db.log_turn(person_id, "assistant", response,
            room_session_id=_room_sid,
            audience_ids=_ct_audience)
```

Same `_compute_room_audience` call per logical-turn (one call, used by both user + assistant log lines). Reduces redundant participants-snapshot reads to once per turn.

---

## 5. `FaceDB.get_recent_room_conversation` — Plan v2 signature

```python
def get_recent_room_conversation(
    self,
    room_session_id: str,
    requester_pid: str,
    best_friend_id: "str | None",
    limit: int = 10,
) -> "list[dict]":
    """P0.S7 D-A — return last ``limit`` turns from ``conversation_log``
    scoped to ``room_session_id``, filtered by audience visibility (T-B
    option β) with best_friend owner override (P1 option ii), with safe
    SQLite LIKE-escape on requester_pid (CRITICAL 1).

    Returns [] on:
      - room_session_id None / empty
      - SQLite OperationalError (logged)
      - No matching rows
    """
```

SQL per §2 above. `_escape_like_pid` helper colocated in `core/db.py` near the method, scoped private (`_` prefix).

---

## 6. `_build_shared_context_block` — Plan v2 signature

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
) -> "str | None":
    """Phase 3B D-A — render <<<SHARED CONTEXT>>> block. Returns None on
    flag-off, single-person, missing room_session_id, or disputed caller (T-A).
    """
```

Same gating order as Plan v1 §6.2:
1. `SHARED_CONTEXT_BLOCK_ENABLED` flag gate
2. `active_session_count < 2` multi-person gate
3. `room_session_id` presence gate
4. `is_disputed_fn(requester_pid)` disputed-skip (T-A)

Render shape unchanged from Plan v1 §6.3 (reuse `_build_cross_person_excerpts` line format).

Prompt-injection placement unchanged from Plan v1 §6.4 (between ROOM and EMOTIONAL CONTEXT blocks).

Call sites unchanged from Plan v1 §6.6 (`conversation_turn` vision_state + `_kairos_tick` vision_state).

---

## 7. Config additions (unchanged from Plan v1 §7)

```python
SHARED_CONTEXT_BLOCK_ENABLED: bool = True
SHARED_CONTEXT_BLOCK_TURN_CAP: int = 10
```

---

## 8. Test specification (Plan v2 — 17 tests)

### Phase 1 tests (FaceDB.get_recent_room_conversation + producer upgrade + helper)

1. **`test_get_recent_room_conversation_returns_audience_visible_rows`** — seed 3 turns with mixed audience_ids `[a]`, `[a, b]`, `[b]`; query as requester `a`; assert returns first 2 rows ordered by ts.
2. **`test_get_recent_room_conversation_legacy_null_audience_visible`** — seed 1 turn with `audience_ids=NULL`; query as requester `a`; assert returns the row (legacy backfill compatibility).
3. **`test_get_recent_room_conversation_best_friend_owner_override`** — seed turn with `audience_ids=[c]`; query as requester `a` with `best_friend_id=a`; assert returns the row (owner override per P1 ii).
4. **`test_get_recent_room_conversation_room_session_id_filter`** — seed 2 turns under different room_session_id values; query for room R1; assert only R1 rows return (no cross-room leak).
5. **`test_get_recent_room_conversation_pid_collision_rejection`** — seed turn with `audience_ids=["jagan_0011"]`; query as requester `jagan_001`; assert returns 0 rows (quote-boundary safety against suffix collision).
6. **`test_get_recent_room_conversation_underscore_wildcard_rejection`** (Plan v2 NEW — CRITICAL 1) — parametrize over `["jaganX001", "jaganA001", "jagan/001", "jagan*001"]` for the X position; seed each as `audience_ids=[that_pid]`; query as `jagan_001`; assert returns 0 rows for each (ESCAPE clause prevents `_` wildcard collision).
7. **`test_get_recent_room_conversation_empty_room_session_id_graceful`** — query with `room_session_id=None`; assert returns `[]` (no exception).
8. **`test_compute_room_audience_speaker_always_present`** (Plan v2 — LOW 5 split, was 8a) — parametrize over (a) empty participants + speaker `j` → `["j"]`, (b) `{"j", "l"}` + speaker `j` → `["j", "l"]` sorted, (c) `{"l"}` + speaker `j` → `["j", "l"]` sorted (speaker added per MEDIUM 4 invariant). Pure helper test.
9. **`test_log_turn_persists_full_room_audience_to_db`** (Plan v2 — LOW 5 split, was 8b) — open 3 sessions in `_session_store` + populate `_active_room_participants`; call `db.log_turn(...)` directly with `audience_ids=_compute_room_audience(...)`; SELECT from `conversation_log`; assert JSON in DB is sorted-list of all 3 pids, NOT `[speaker_pid]`.

### Phase 2 tests (`_build_shared_context_block` + pipeline integration)

10. **`test_shared_context_block_renders_multi_person`** — mock `FaceDB.get_recent_room_conversation` to return 2 turns; assert block contains the markers + 2 lines + correct format.
11. **`test_shared_context_block_single_person_returns_none`** — `active_session_count=1`; assert returns None.
12. **`test_shared_context_block_flag_off_returns_none`** — monkeypatch `SHARED_CONTEXT_BLOCK_ENABLED=False`; assert returns None.
13. **`test_shared_context_block_disputed_caller_returns_none`** (T-A) — `is_disputed_fn` returns True; assert returns None AND `db.get_recent_room_conversation` is NOT called (disputed gate fires before DB fetch).
14. **`test_shared_context_block_injected_in_build_system_prompt`** — source-inspection test asserting `_build_system_prompt` calls `_build_shared_context_block` AND that the call site is between ROOM block injection and EMOTIONAL CONTEXT injection (Plan v2 §6 ordering).

### Phase 3 tests (AST source-inspection invariants)

15. **`test_log_turn_callers_use_compute_room_audience_helper`** — AST scan pipeline.py for `db.log_turn(` calls; assert each of the 5 call sites uses `audience_ids=<var_from_compute_room_audience>` (var-traceback OR direct call), NOT `audience_ids=[<single_pid>]`.
16. **`test_shared_context_block_disputed_guard_present`** — AST scan `_build_shared_context_block` body; assert `is_disputed_fn(requester_pid)` is invoked BEFORE any `db.get_recent_room_conversation(...)` call.
17. **`test_facedb_get_recent_room_conversation_signature`** — AST scan FaceDB class; assert the method has the Plan v2 §5 signature (4 kwargs: room_session_id, requester_pid, best_friend_id, limit — `since_ts` MUST NOT be present).

### Phase 4 (deliberate-regression confirmations — closure items, not pytest)

- **(a)** Inject `audience_ids=[pid]` in one log_turn caller → Phase 3 test 15 fires.
- **(b)** Inject `db.get_recent_room_conversation(...)` call BEFORE `is_disputed_fn(...)` check → Phase 3 test 16 fires.
- **(c)** Inject pid-wildcard-collision row (`audience_ids=["jaganX001"]`) in seed; query as `jagan_001` → Phase 1 test 6 fires (CRITICAL 1 regression guard).
- **(d)** Drop the `room_session_id = ?` clause from the SQL → Phase 1 test 4 fires (cross-room leak).
- **(e)** Drop the `_compute_room_audience` speaker-presence invariant (case c) → Phase 1 test 8 fires (MEDIUM 4 regression guard).

**Net new tests: 17.** Plan v1 16 → Plan v2 17 (+1 underscore wildcard test, -1 since_ts test dropped, +1 test 8 split).

**Suite delta: 2310 → 2327.**

---

## 9. Implementation phases (Plan v2 — revised test counts)

### Phase 1 — Storage layer + producer upgrade + helper (+9 tests)

- New `_escape_like_pid` helper in `core/db.py`
- New `FaceDB.get_recent_room_conversation` method (Plan v2 §5)
- New `_compute_room_audience` helper in `pipeline.py` (Plan v2 §4.2)
- Producer-side audience_ids upgrade at all 5 log_turn call sites (Plan v2 §4.3)
- Phase 1 tests 1-9 from §8
- **Suite checkpoint:** 2310 → 2319 (+9)

### Phase 2 — Consumer + prompt integration (+5 tests)

- New `_build_shared_context_block` helper (Plan v2 §6)
- 2 call sites: `conversation_turn` + `_kairos_tick`
- `_build_system_prompt` injection between ROOM and EMOTIONAL CONTEXT
- 2 config additions (Plan v2 §7)
- Phase 2 tests 10-14 from §8
- **Suite checkpoint:** 2319 → 2324 (+5)

### Phase 3 — Structural invariants (+3 tests)

- 3 AST source-inspection tests (Plan v2 §8 tests 15-17)
- **Suite checkpoint:** 2324 → 2327 (+3)

### Phase 4 — Deliberate-regression confirmations + closure (+0 tests)

- 5 deliberate-regression confirmations per Plan v2 §8 Phase 4 list
- Closure-report banking (same as Plan v1 §9)

---

## 10. Latency budget (Plan v2 — LOW 6 revision)

Plan v1 test 1's assertion changes from single-shot to median-of-10:

```python
def test_get_recent_room_conversation_latency_under_budget():
    # ... setup: seed 100 turns under a single room_session_id ...
    measurements_ms: list[float] = []
    for _ in range(10):
        t0 = time.perf_counter()
        rows = db.get_recent_room_conversation(
            room_session_id="room_test",
            requester_pid="jagan_001",
            best_friend_id="jagan_001",
            limit=10,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        measurements_ms.append(elapsed_ms)
    median_ms = statistics.median(measurements_ms)
    assert median_ms < 50.0, (
        f"P0.S7 latency p50={median_ms:.1f}ms exceeds 50ms budget; "
        f"all measurements: {[round(m, 1) for m in measurements_ms]}"
    )
```

**Why median-of-10 (not p95 or p99):** statistically meaningful at N=10 (p95 would require N≥20 to be robust); reduces single-outlier flake without inflating CI cost.

**Production target:** <10ms p99. CI assertion is <50ms p50 — generous margin for CI runners (cold-start, neighbor noise). If real production exceeds the production target, Plan v3 (future) can add per-room-key caching or the json_each migration (D4.b).

---

## 11. Token-budget impact (unchanged from Plan v1 §11)

Validation-window overlap accepted per Plan v1 §11. ~+300 tokens worst-case (~+2% of 18k-token prompt). D-C cleanup is the structural fix; lands as separate canary-gated follow-up.

---

## 12. Validation gate (Plan v2 closure criteria)

1. All 17 new tests green + full-suite green at 2327.
2. 5/5 deliberate-regression confirmations pass (induction protocol).
3. Latency p50 < 50ms verified in Phase 1 test 1 (median-of-10, LOW 6).
4. 3 missed threats from Phase 0 audit (T-A / T-B / T-C) resolved with explicit non-claim documentation in closure report.
5. 6 Plan v1 precision items (2 CRITICAL + 4 MEDIUM/LOW) resolved in closure report.
6. D-precision items 1 + 2 (Plan v1) resolution documented in closure report.

---

## 13. Discipline-count predictions (unchanged from Plan v1 §13)

- Spec-first review cycle: **8-for-8 → 9-for-9** on closure
- Sub-pattern A: 3rd → **4th instance** banked as memory-note (still NOT elevated to standalone `###` doctrine; 5+ threshold)
- Tripwires-must-match-deferral-surface: stays **4-for-4** (no tripwire-guarded deferral introduced)
- Developer-improves-on-spec: stays **6-for-6** unless code phase surfaces a mechanism improvement
- Induction-surfaces-invariant-gaps: stays **7-for-7** unless Phase 4 surfaces a real gap

---

## 14. Open items / risks (Plan v2 extensions)

1. **Jetson SQLite version unverified.** D4.a locked; Plan v3 may revise if Jetson SQLite ≥3.45 verified AND LIKE-with-ESCAPE surfaces a bug. The Python-side escape approach (Plan v2 §2) is SQLite-version-independent so the bound on this risk is "performance," not "correctness."
2. **`_active_room_participants` race during turn-flight.** Defensive fallback in `_compute_room_audience` (Plan v2 §4.2 cases a + c) covers both empty + speaker-missing races. The invariant "speaker is ALWAYS in audience" is structurally guaranteed.
3. **D-C cleanup not gated on D-A closure.** Independent. D-C still requires the live multi-person canary that hasn't run.
4. **Backfill-row visibility semantics.** Audience-NULL legacy rows are visible to ALL room members (S107 backfill default). Preserved unchanged.
5. **D-A retrieval contract does NOT account for room continuity across system reboots.** If room_session_id is re-minted across boots, old room's turns are scoped out by the `room_session_id = ?` filter. Same as Plan v1 §14 item 5. Plan v3 may add "same participants within N minutes" union if Jagan reports the UX issue.
6. **Long-running-session in-memory-vs-DB overlap** (CRITICAL 2 acceptance): if a single session lives long enough that ROOM block + SHARED CONTEXT render overlapping content, brain reads it as "consistent context with reinforcement." If production shows brain-side confusion, Plan v3 revisits real dedup (CRITICAL 2 option b in auditor's verdict).

---

## 15. Reference documents

- `tests/p0_s7_audit.md` — Phase 0 audit (premise reset; 5-deferral decomposition; D-A first slice)
- `tests/p0_s7_plan_v1.md` — Plan v1 (retained for delta visibility)
- `everything_about_system.md` §145 (Q3 History Architecture Redesign), §163 (Room session lifecycle), §163.3 (RoomOrchestrator class non-goal)
- `CLAUDE.md` Sessions 107 (schema), 111 (addressed_to), 112 (room lifecycle), 113 (3B.1-3B.6 features)
- `core/db.py:1278` (existing `search_room_turns` S113 — reference shape for `get_recent_room_conversation`)
- `core/faces_db_migrations.py:173-204` (v=7 room schema), `:217-250` (v=9 backfill)
- `pipeline.py` lines 3205, 3208, 5103, 5996, 5998 — grep-verified 5 log_turn call sites (Plan v2 §4.1 exhaustive enumeration)
- `pipeline.py:1166` (`_build_cross_person_excerpts` — D7.a render-shape source), `:1288` (`_build_room_block` — placement reference), `:5216` (D-C future cleanup target)
- `tests/p0_s6_plan_v2.md` — reference Plan v2 shape
- `tests/p0_s1_plan_v2.md` — reference 4-phase implementation shape
