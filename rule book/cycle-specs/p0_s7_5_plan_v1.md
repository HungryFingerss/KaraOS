# P0.S7.5 — Bundled-queue canary follow-up — Plan v1

**Date:** 2026-05-19
**Author:** architect
**Status:** Plan v1 — locked at FULL scope (D1+D2+D3 opt(a)+D4+D5) per auditor verdict 2026-05-19. Standing by for auditor review.

**Companion documents:**
- `tests/p0_s7_5_audit.md` — Phase 0 audit (APPROVED with 6 adjudications locked)
- `tests/p0_s7_5_plan_v2.md` — forthcoming if precision items surface (likely 2-3 per auditor estimate)

**Disciplines applied:**
- **Two-pass grep-verification (Pass 1)**: all function/line references grep-verified 2026-05-19 at drafting. Pass 2 fires at closure.
- **AST forward-property + behavioral workhorse pair**: §7 test design preserves the discipline.
- **Spec-contracts-not-implementations**: D-decisions specify contracts; developer chooses mechanism within them where applicable.
- **Auditor-Q5-estimates-trail-grep** (architect-memory, 3 instances pre-P0.S7.5): pre-emptive estimate 12-19 tests; §6.3 grep-verifies → 4th instance banked at closure.

---

## 1. Auditor-locked scope (per Phase 0 verdict 2026-05-19)

**FULL scope (§6.1 of audit) — D1 + D2 + D3 + D4 + D5.** No deferred items. All 5 D-decisions are root-cause fixes for canary-observed failures.

| ID | D-decision | Severity | Source |
|---|---|---|---|
| D1 | VISITOR_ALERT nudge persistence via `_ONE_SHOT_NUDGE_TYPES` frozenset | LOAD-BEARING | Canary turn 79 fabricated denial |
| D2 | SHARED CONTEXT gate widening (audience-match fallback branch) | LOAD-BEARING | Canary `gate=single_person → skip` traces |
| D3 | Canonical ack race fix — option (a) `await _session_store.rename` | UX (MEDIUM) | Canary "Got it, visitor." after Lexi rename |
| D4 | `update_person_name` description tightening + `<<<KNOWN SPEAKER IDENTITY>>>` block | MEDIUM | Canary 5 repeated `update_person_name({'name':'Lexi'})` calls |
| D5 | HONESTY POLICY "fabricated absence" anti-pattern | LOW | Canary "No one was here / I was just waiting" confabulation |

**6 adjudications from Phase 0 verdict (all matching architect's lean):**
1. §6 scope — FULL (✓)
2. §1.3 sub-pattern A — stays at 5 instances (✓ strict-read held)
3. §5.1 partial-falsification framing — defer CLAUDE.md banking to 3+ instances (✓ tentative)
4. §7.4 D3 variant — option (a) `await` (✓ architect's revised lean)
5. §7.2 D1 re-injection — ship simple now; defer auto-dismiss (✓)
6. Bundled-queue RE-CANARY trigger — IMMEDIATELY after closure (✓ no observation window)

---

## 2. Pass 1 grep verification (2026-05-19 at Plan v1 drafting)

### 2.1 Nudge type enumeration (D1)

Production nudge types found via grep:

| Type | Site | Semantic |
|---|---|---|
| `VISITOR_ALERT` | `core/brain_agent.py:7175` (queued) | Owner-facing context: someone visited while owner away |
| `CROSS_PERSON_HYPOTHESIS` | `core/brain_agent.py:6190, :6234` | Proactive nudge: "you both mentioned X" |
| `INTENTION_FOLLOWUP` | `core/brain_agent.py:6264` | Proactive nudge: "you said you'd call X" |
| `MEMORY_PROMPT` | `core/brain_agent.py:6291` | Proactive nudge: "you mentioned X earlier" |

**4 types total.** 3 are PROACTIVE (one-shot is correct — nudge should not repeat); 1 is PERSISTENT context (VISITOR_ALERT — owner needs it whenever asked).

**Architect's framing decision**: enumerate the ONE-SHOT types explicitly (3 entries). New nudge types DEFAULT TO PERSISTENT (the safe behavior — don't lose context). Developer must explicitly add new types to the frozenset to opt in to one-shot.

Rationale for default-to-persistent over default-to-one-shot:
- The canary failure mode was nudge LOSS (consumed too early). Defaulting new types to persistent fails-safe: new context never gets lost.
- One-shot intent is explicit (proactive nudges). Persistent intent is the broader category.
- If a new ONE-SHOT type is added without registering in the frozenset, worst case is "nudge re-injects until expires" — annoying but not load-bearing failure. Inverse default would worst-case as "nudge lost permanently" — repeats the P0.S7.5 canary failure mode.

### 2.2 Visitor alert + injection chain (D1)

| File | Line | Surface |
|---|---|---|
| `core/brain_agent.py` | 7075-7190 | `_run_visitor_alert(person_id)` — queues nudge with `[visitor_name:X]` + `[visitor_id:Y]` markers |
| `core/brain_agent.py` | 8342-8363 | `PromptPrefAgent.get_prompt_addendum` — **D1 PRIMARY EDIT SITE** |
| `core/brain_agent.py` | 2934-2952 | `BrainDB.get_pending_nudges` filter |
| `core/brain_agent.py` | 3063-3068 | `BrainDB.mark_nudge_injected` write |

### 2.3 SHARED CONTEXT block (D2)

| File | Line | Surface |
|---|---|---|
| `core/room_orchestrator.py` | 231-310 | `RoomOrchestrator.build_shared_context_block` |
| `core/room_orchestrator.py` | 261-264 | **D2 PRIMARY EDIT SITE** — narrow gate `if active_session_count < 2: skip` |
| `core/db.py` | 1296-1371 | `FaceDB.get_recent_room_conversation(room_session_id, requester_pid, ...)` — room-scoped; reused by D2 |
| (new) | — | `FaceDB.get_recent_audience_rooms(requester_pid, best_friend_id, hours_back, limit)` — **NEW HELPER for D2** |

### 2.4 Canonical ack race (D3)

| File | Line | Surface |
|---|---|---|
| `pipeline.py` | 3439 | `_handle_update_person_name` is `async def` ✓ — can `await` |
| `pipeline.py` | 3766-3770 | **D3 PRIMARY EDIT SITE** — currently `_loop.create_task(_session_store.rename(...))`; change to `await _session_store.rename(...)` |
| `pipeline.py` | 5777-5781 | Ack template — reads `peek_snapshot` AFTER handler returns; under D3 fix, snapshot reflects post-rename state |
| `core/session_state.py` | 317-321 | `SessionStore.rename(pid, new_name)` is `async def` ✓ — directly awaitable |

### 2.5 update_person_name description + KNOWN SPEAKER IDENTITY block (D4)

| File | Line | Surface |
|---|---|---|
| `core/brain.py` | 199-236 | `update_person_name` tool description — **D4 EDIT SITE 1** (extend with Bug Q-equivalent) |
| `core/brain.py` | 249-252 | `update_system_name` Bug Q reference text (template for parallel) |
| `core/brain.py` | 2013-2049 | `format_system_identity_block(system_name)` helper (template for parallel `format_known_speaker_identity_block`) |
| `core/brain.py` | (call site of SYSTEM IDENTITY block) | Insertion point for new KNOWN SPEAKER IDENTITY block — **D4 EDIT SITE 2** |
| `core/config.py` | (lookup) | `SYSTEM_IDENTITY_BLOCK_ENABLED` flag (template for new `KNOWN_SPEAKER_IDENTITY_BLOCK_ENABLED`) |

### 2.6 HONESTY POLICY fabricated-absence anti-pattern (D5)

| File | Line | Surface |
|---|---|---|
| `core/brain.py` | 2222-2311 | `<<<HONESTY POLICY>>>` block (in `_build_system_prompt`) |
| `core/brain.py` | 2311 | `<<<END HONESTY POLICY>>>` closing marker — **D5 INSERT BEFORE THIS LINE** |
| `core/config.py` | (lookup) | `HONESTY_POLICY_BLOCK_ENABLED` flag (existing; gate the new anti-pattern bullet under it) |

### 2.7 Test surface count (Auditor-Q5 4th instance banking)

Pre-emptive estimate from Phase 0 §5.3: **12-19 tests**.

Plan v1 lock per D-decision breakdown:

| D | Phase 1 unit | Phase 2 AST | Phase 3 behavioral | Phase 4 confirmations | Total |
|---|---|---|---|---|---|
| D1 | 3 (frozenset content + persistent VISITOR_ALERT + one-shot CROSS_PERSON) | 1 (mark_injected call site gated) | 1 (multi-turn injection scenario) | — | 5 |
| D2 | 2 (new helper + gate widening unit) | 1 (gate widening structure AST) | 1 (cross-session retrieval behavioral) | — | 4 |
| D3 | 1 (rename `await` source-inspection) | — | 1 (canonical ack returns new name behavioral) | — | 2 |
| D4 | 2 (description content + KNOWN SPEAKER IDENTITY block content) | 1 (gating on person_type) | 1 (repeat-suppression behavioral) | — | 4 |
| D5 | 1 (anti-pattern bullet content) | — | — | — | 1 |
| **Total** | **9** | **3** | **4** | (4 dry-runs against existing tests) | **16** |

**Plan v1 forecast: +16 tests** (within auditor's 12-19 range).

**Auditor-Q5-estimates-trail-grep 4th instance** banking: auditor estimated 12-19; Plan v1 lands at 16 (mid-range). **First on-target estimate across 4 instances** (D-B was high by 40%, D-D was low by 4×, D-E was low by 60%). Pattern: estimate accuracy correlates with audit-Phase 0 granularity — the more decomposed the Phase 0 D-decisions, the more accurate the auditor's estimate. P0.S7.5 had 5 D-decisions each with concrete edit sites; D-D had aggregated framing of "7 helpers." Bank this observation toward potential 5+ doctrine elevation.

---

## 3. D1 — VISITOR_ALERT nudge persistence

### 3.1 Contract

`PromptPrefAgent.get_prompt_addendum(person_id)` MUST NOT call `mark_nudge_injected` for nudges whose `nudge_type` is NOT in `_ONE_SHOT_NUDGE_TYPES`. Non-one-shot nudges (VISITOR_ALERT) remain pending; subsequent calls to `get_pending_nudges` continue to return them until naturally expired (`expires_at` past) OR dismissed (`dismissed_at` set).

### 3.2 New constant

In `core/config.py` (alongside other proactive-nudge config):

```python
# P0.S7.5 D1 — nudge types that are ONE-SHOT proactive reminders.
# These get mark_nudge_injected on first delivery (legacy behavior).
# Nudge types NOT in this set default to PERSISTENT context — they
# stay pending and re-inject every turn until expires_at or dismissed.
# VISITOR_ALERT is INTENTIONALLY excluded: owner needs persistent
# context about visitor presence whenever they ask, not just first turn.
# When adding a new nudge type, default behavior is PERSISTENT — opt
# into one-shot only when the type is a proactive reminder that
# should not repeat.
_ONE_SHOT_NUDGE_TYPES: frozenset[str] = frozenset({
    "CROSS_PERSON_HYPOTHESIS",
    "INTENTION_FOLLOWUP",
    "MEMORY_PROMPT",
})
```

### 3.3 Edit at `PromptPrefAgent.get_prompt_addendum`

Production-code shape contract:

```python
def get_prompt_addendum(self, person_id: str) -> str | None:
    parts: list[str] = []
    pref_text = self._brain_db.get_prompt_addendum(person_id)
    if pref_text:
        parts.append(pref_text)
    nudges = self._brain_db.get_pending_nudges(person_id, limit=1)
    if nudges:
        nudge = nudges[0]
        parts.append(
            f"[Proactive — work naturally into conversation if the moment fits: "
            f"{nudge['content']}]"
        )
        # D1: only mark one-shot types as injected. Persistent context
        # types (VISITOR_ALERT) stay pending until naturally expired or
        # dismissed — owner needs them whenever they ask, not just
        # on first re-engagement turn.
        from core.config import _ONE_SHOT_NUDGE_TYPES
        if nudge.get("nudge_type") in _ONE_SHOT_NUDGE_TYPES:
            self._brain_db.mark_nudge_injected(nudge["id"])
    if parts:
        print(
            f"[PromptPrefAgent] {len(parts)} addendum part(s) injected for {person_id} "
            f"(prefs={'yes' if pref_text else 'no'}, nudge={'yes' if nudges else 'no'})"
        )
    return "\n\n".join(parts) if parts else None
```

### 3.4 `get_pending_nudges` returns nudge_type

Grep-verified `core/brain_agent.py:2947-2952` already returns `nudge_type` in the dict shape. No DB schema change. No `get_pending_nudges` signature change.

### 3.5 Backwards-compat with existing nudge types

The other 3 nudge types (`CROSS_PERSON_HYPOTHESIS`, `INTENTION_FOLLOWUP`, `MEMORY_PROMPT`) keep their existing one-shot behavior via explicit frozenset membership. No regression on those code paths.

### 3.6 Re-injection cost note

Per auditor Q5 verdict — ship simple re-injection now; defer `auto_dismiss_on_acknowledge` to follow-up if re-canary surfaces cost concern. The `expires_at = time.time() + 86400` (24h ceiling per `_run_visitor_alert` line 7184) bounds worst case naturally.

---

## 4. D2 — SHARED CONTEXT gate widening

### 4.1 Contract

`RoomOrchestrator.build_shared_context_block` MUST render persisted room turn excerpts when the CURRENT scene is single-person AND the requester has recent room participation (within `SHARED_CONTEXT_RECENT_AUDIENCE_HOURS` window). The existing fast-path (multi-person scene) stays unchanged. The audience filtering at retrieval time is unchanged (already correct per P0.S7 D-A).

### 4.2 New DB helper

In `core/db.py` (alongside `get_recent_room_conversation`):

```python
def get_recent_audience_rooms(
    self,
    requester_pid: str,
    best_friend_id: "str | None" = None,
    hours_back: float = 24.0,
    limit: int = 5,
) -> "list[str]":
    """P0.S7.5 D2 — return distinct room_session_ids from the past
    ``hours_back`` window where requester_pid appears in audience_ids
    OR requester is the best_friend (owner override per 3A.4.6).

    Used by RoomOrchestrator.build_shared_context_block when current
    scene is single-person but owner returns and asks about prior
    multi-person rooms.

    Returns ordered list (most-recent first) of distinct room_session_id
    strings. Empty list when no qualifying rooms.

    Visibility composition mirrors get_recent_room_conversation:
      - best_friend owner override → all rooms regardless of audience
      - audience_ids LIKE-substring contains requester_pid (with ESCAPE)
      - audience_ids IS NULL → legacy backfill, default-visible

    SQL invariants:
      - WHERE ts >= (now - hours_back * 3600)
      - WHERE room_session_id IS NOT NULL
      - ORDER BY MAX(ts) DESC GROUP BY room_session_id
      - LIMIT limit
    """
```

Implementation contract (developer chooses exact SQL within these constraints):
- Reuse `_escape_like_pid` helper for safe LIKE substring with ESCAPE clause (per CRITICAL 1 from P0.S7 D-A — the existing pattern at line 1341 of db.py)
- Use SQLite's existing `idx_conv_log_room` index where possible
- Defensive try/except matching `get_recent_room_conversation` shape — log `OperationalError` and return `[]`

### 4.3 New config constant

In `core/config.py`:

```python
# P0.S7.5 D2 — SHARED CONTEXT widening window. When current scene
# is single-person but the requester appears in recent room sessions'
# audience_ids within this window, render persisted history from
# those rooms. Matches the visitor-alert expiry (24h) so the two
# defenses align temporally.
SHARED_CONTEXT_RECENT_AUDIENCE_HOURS: float = 24.0
```

### 4.4 Gate widening at `build_shared_context_block`

Production-code shape contract for the new fallback branch:

```python
# Existing fast path (D-A semantic, multi-person scene)
if active_session_count >= 2 and room_session_id:
    # ... existing query against current room_session_id ...
    return _render(...)

# D2 fallback path — single-person scene OR no current room_session_id,
# but check for recent room participation.
if active_session_count < 2 or not room_session_id:
    from core.config import SHARED_CONTEXT_RECENT_AUDIENCE_HOURS
    recent_room_ids = db.get_recent_audience_rooms(
        requester_pid=requester_pid,
        best_friend_id=best_friend_id,
        hours_back=SHARED_CONTEXT_RECENT_AUDIENCE_HOURS,
        limit=5,
    )
    if not recent_room_ids:
        _pl._last_shared_context_row_count = 0
        print(
            f"[SharedContext] gate=single_person + no_recent_audience "
            f"(count={active_session_count}) → skip"
        )
        return None
    # Query each recent room's persisted history; merge ordered by ts
    all_rows: list[dict] = []
    for rid in recent_room_ids:
        rows = db.get_recent_room_conversation(
            room_session_id=rid,
            requester_pid=requester_pid,
            best_friend_id=best_friend_id,
            limit=limit,
        )
        all_rows.extend(rows)
    if not all_rows:
        _pl._last_shared_context_row_count = 0
        print(
            f"[SharedContext] gate=recent_audience_empty "
            f"(rooms={len(recent_room_ids)}) → skip"
        )
        return None
    # Sort merged rows chronologically + cap at limit
    all_rows.sort(key=lambda r: r["ts"])
    if len(all_rows) > limit:
        all_rows = all_rows[-limit:]
    _pl._last_shared_context_row_count = len(all_rows)
    print(
        f"[SharedContext] gate=recent_audience "
        f"(rooms={len(recent_room_ids)}, rows={len(all_rows)}) → render"
    )
    return _render(all_rows, ...)
```

### 4.5 Disputed-caller / flag-off gates preserved

The new fallback branch runs AFTER existing flag-off + disputed-caller gates. Those gates apply uniformly to both fast-path and fallback path. Implementation contract: developer arranges gate ordering so disputed-caller fail-closes BEFORE the new fallback runs.

### 4.6 Privacy contract preserved

The new helper `get_recent_audience_rooms` filters by audience_ids the same way as `get_recent_room_conversation`. The subsequent per-room queries via `get_recent_room_conversation` also enforce audience filtering. No privacy regression possible.

---

## 5. D3 — Canonical ack race fix (option (a) `await`)

### 5.1 Contract

`_handle_update_person_name` MUST complete the session-store rename BEFORE returning. The downstream `peek_snapshot` in `conversation_turn` MUST observe the post-rename name.

### 5.2 Single-line fix

At `pipeline.py:3766-3770` (current code):

```python
try:
    _loop = asyncio.get_running_loop()
    _loop.create_task(_session_store.rename(person_id, new_name))
except RuntimeError:
    pass  # OPTIONAL: no running loop in test/early-boot context
```

Replace with:

```python
# D3 (P0.S7.5) — await rename synchronously so the downstream
# canonical-ack template peek_snapshot observes the new name.
# Previous fire-and-forget create_task was racy (canary 2026-05-19
# 21:04:24 "Got it, visitor." instead of "Got it, Lexi.").
try:
    await _session_store.rename(person_id, new_name)
except Exception as _rn_e:
    # Preserve old graceful-degrade semantic for test contexts.
    print(f"[Pipeline] _session_store.rename failed: {_rn_e!r}")  # OPTIONAL
```

The handler is `async def` (verified §2.4) so the `await` is in scope.

### 5.3 Other create_task sites in same handler stay async

`_session_store.promote_type`, `set_cached_prefix`, `set_waiting_for_name` at lines 3786-3788 stay as `create_task` — they're not on the ack path and don't need synchronization with the snapshot read.

### 5.4 Edge case: test contexts without running loop

The original code wrapped in `try: ... except RuntimeError: pass` to handle test contexts where `asyncio.get_running_loop()` raises. With `await`, the `RuntimeError` is impossible (we're already inside an `await`-context — the loop IS running). The new try/except handles arbitrary `Exception` from the rename itself (defensive); failure logs but does not raise into the dispatcher.

---

## 6. D4 — `update_person_name` description tightening + `<<<KNOWN SPEAKER IDENTITY>>>` block

### 6.1 Contract

The `update_person_name` tool MUST emit explicit Bug Q-equivalent anti-repeat language in its description (parallel to `update_system_name`). A new `<<<KNOWN SPEAKER IDENTITY>>>` system-prompt block MUST surface "you know this person's name; do NOT call update_person_name unless they correct it" when the current speaker's `person_type` is `known` or `best_friend`.

### 6.2 Tool description extension

At `core/brain.py:199-228` (current `update_person_name` description), APPEND the following bullet before the closing `)`:

```python
"\n\n"
"CRITICAL — DO NOT RE-CONFIRM (Bug Q parallel, 2026-05-19): If the "
"current speaker's person_type is already 'known' or 'best_friend' "
"AND the sensor block's `who=` field shows the same name you would "
"pass, the tool call is a no-op — answer verbally instead. The "
"tool is for ESTABLISHING the name (stranger promotion) or "
"CHANGING it (the speaker corrects to a different name). Calling "
"it as a confirmation of the existing name creates a feedback "
"loop: the LLM hears its own canonical-ack and re-issues the same "
"call next turn. Canary 2026-05-19: brain re-issued "
"`update_person_name({'name':'Lexi'})` 5 times after Lexi was "
"already renamed. Do NOT call when the sensor already shows the "
"name and the speaker has not actively requested a change."
```

### 6.3 New helper `format_known_speaker_identity_block`

In `core/brain.py` (after `format_system_identity_block` at line 2013):

```python
def format_known_speaker_identity_block(
    person_name: str,
    person_type: str,
) -> str:
    """P0.S7.5 D4 — render the `<<<KNOWN SPEAKER IDENTITY>>>` block
    when the current speaker is known (not stranger). Mirror of
    `format_system_identity_block` for person renames.

    Surfaces the speaker's established name to the LLM so the
    update_person_name tool is not called as a confirmation of the
    already-known name. Block fires only when person_type IN
    {'known', 'best_friend'}; strangers correctly receive promotion
    prompting via the STRANGER IDENTITY block (Session 97).

    Block content covers:
      - The speaker's name is X (already established)
      - Do NOT call update_person_name unless the speaker corrects
        to a DIFFERENT name
      - Examples of correction shapes vs casual mention
      - Anti-feedback-loop framing matching system_name Bug Q
    """
```

Contract for block content (developer writes exact wording within these constraints):
- Open with "Your conversation partner's name is {person_name}. They are person_type='{person_type}'."
- Numbered rules:
  1. Do NOT call `update_person_name` to confirm the existing name. The name is established.
  2. ONLY call when the speaker EXPLICITLY corrects to a DIFFERENT name. Examples: "Actually I'm not Lexi, I'm Lexie", "Call me Lex instead."
  3. Examples that are NOT correction requests:
     - "{person_name} said earlier..." (mentioning self by name — not a rename)
     - "Hi, it's {person_name}" (greeting — not a rename)
     - Any sentence where the speaker uses their own name in conversation
- Reference Bug Q parallel framing — the loop concern matches `update_system_name`.

### 6.4 New config flag

In `core/config.py`:

```python
# P0.S7.5 D4 — gate the KNOWN SPEAKER IDENTITY block. Default True;
# rollback is a one-line flip if the block proves too verbose for
# normal turns.
KNOWN_SPEAKER_IDENTITY_BLOCK_ENABLED: bool = True
```

### 6.5 Block insertion in `_build_system_prompt`

Block renders AFTER `<<<SYSTEM IDENTITY>>>` (which gates on the AI's own name being set) and BEFORE `<<<HONESTY POLICY>>>`. Gate on:

```python
if (
    KNOWN_SPEAKER_IDENTITY_BLOCK_ENABLED
    and person_name
    and session_person_type in ("known", "best_friend")
):
    prompt += format_known_speaker_identity_block(person_name, session_person_type)
```

### 6.6 Stranger session interaction

The Session 97 STRANGER IDENTITY block already fires when `session_person_type == "stranger"` AND turn_count >= 2. KNOWN SPEAKER IDENTITY block fires ONLY when person_type IS `known`/`best_friend`. The two are MUTUALLY EXCLUSIVE — no overlap in conditions, no double-rendering.

---

## 7. D5 — HONESTY POLICY "fabricated absence" anti-pattern

### 7.1 Contract

The `<<<HONESTY POLICY>>>` block MUST include an explicit anti-pattern bullet that forbids confabulated absence-of-presence claims ("no one was here", "I was just waiting", "nothing happened") without conclusive retrieved evidence the room was empty during the period in question.

### 7.2 Bullet content

Insert BEFORE the closing `<<<END HONESTY POLICY>>>` marker at `core/brain.py:2311`:

```python
"- FABRICATED ABSENCE (Session P0.S7.5 canary 2026-05-19): NEVER "
"claim \"no one was here\", \"I was alone\", \"nothing happened\", "
"\"I was just waiting for you\", or similar absence-of-presence "
"statements WITHOUT conclusive retrieved evidence the room was "
"empty during the period in question. Absence of memory is NOT "
"evidence of absence. If you searched and got empty results, "
"hedge honestly (\"I checked and don't have clear records of who "
"was here during that period — can you remind me?\") instead of "
"asserting nobody was there. The canary failure: brain answered "
"\"No one, Jagan, I was just waiting for you to come back\" when "
"Lexi had in fact visited; this is a fabrication on TWO axes — "
"(a) asserting nobody visited (no retrieval evidence supports "
"this), (b) describing the brain's own activity (\"just waiting\") "
"which is also fabricated. NEVER fabricate either axis.\n"
```

### 7.3 Block-flag gating

The bullet inherits the existing `HONESTY_POLICY_BLOCK_ENABLED` flag (gates the entire block). No new flag needed.

### 7.4 Test surface

Single source-inspection test: assert the bullet text contains the load-bearing anchors ("FABRICATED ABSENCE", "no one was here", "Absence of memory is NOT evidence of absence", "fabrication on TWO axes").

---

## 8. Phase decomposition

### 8.1 Phase 1 — D1 + D2 unit tests (~4 hours)

Surfaces shipped:
- `_ONE_SHOT_NUDGE_TYPES` frozenset in `core/config.py`
- Edit at `PromptPrefAgent.get_prompt_addendum` (gate mark_injected on type membership)
- New `FaceDB.get_recent_audience_rooms` helper in `core/db.py`
- `SHARED_CONTEXT_RECENT_AUDIENCE_HOURS` constant in `core/config.py`
- D2 fallback branch in `RoomOrchestrator.build_shared_context_block`

Tests (5):
- (1) `_ONE_SHOT_NUDGE_TYPES` contains exactly {`CROSS_PERSON_HYPOTHESIS`, `INTENTION_FOLLOWUP`, `MEMORY_PROMPT`}; `VISITOR_ALERT` NOT in set.
- (2) `get_prompt_addendum` calls `mark_nudge_injected` for one-shot type; does NOT call for VISITOR_ALERT.
- (3) `get_recent_audience_rooms` returns rooms within window; respects best_friend override; respects audience filter; returns `[]` outside window.
- (4) `build_shared_context_block` widening branch fires when current scene single-person but recent rooms exist; returns None when no recent rooms.
- (5) Existing multi-person fast path still returns expected output (regression guard).

### 8.2 Phase 2 — D3 + D4 + D5 ship (~3 hours)

Surfaces:
- `await _session_store.rename` at `pipeline.py:3766-3770`
- `update_person_name` description extension at `core/brain.py:199-236`
- `format_known_speaker_identity_block` helper + block insertion in `_build_system_prompt`
- `KNOWN_SPEAKER_IDENTITY_BLOCK_ENABLED` config flag
- HONESTY POLICY fabricated-absence bullet at `core/brain.py:2311`

Tests (8):
- (6) AST: `_handle_update_person_name` body contains `await _session_store.rename`; does NOT contain `create_task(_session_store.rename`.
- (7) Behavioral: canonical ack reads new name post-rename (seed session, fire tool, assert response text contains new_name not old_name).
- (8) `update_person_name` description contains "CRITICAL — DO NOT RE-CONFIRM" + "feedback loop" anchors.
- (9) `format_known_speaker_identity_block` renders with person_name + person_type interpolated; contains "DO NOT call update_person_name" + correction example anchors.
- (10) AST: block insertion in `_build_system_prompt` gated on `session_person_type in ("known", "best_friend")` AND `KNOWN_SPEAKER_IDENTITY_BLOCK_ENABLED`.
- (11) Behavioral: stranger session does NOT receive KNOWN SPEAKER IDENTITY block (mutual exclusion with STRANGER IDENTITY block).
- (12) HONESTY POLICY block contains FABRICATED ABSENCE bullet with required anchors.
- (13) Block flag off → entire HONESTY POLICY absent (regression guard on existing flag).

### 8.3 Phase 3 — Behavioral integration (~1.5 hours)

Surfaces tested:
- End-to-end visitor alert persistence: queue alert + simulate multi-turn re-engagement + assert VISITOR CONTEXT block renders for ≥2 turns.
- SHARED CONTEXT widening: persist conversation_log rows + simulate owner-returns scenario + assert widened gate fires.
- update_person_name repeat-suppression: known session + repeated tool calls + assert tool repeat guard catches.

Tests (3):
- (14) E2E nudge persistence: VISITOR_ALERT queued; first call injects (nudge=yes); second call STILL injects (nudge=yes; persistent); only stops when expired or dismissed.
- (15) E2E SHARED CONTEXT widening: 2-person room session ends, owner returns alone → `build_shared_context_block` returns persisted history rows.
- (16) E2E update_person_name repeat: known-session brain re-issues `update_person_name({'name': 'Lexi'})` → handler returns `handled_noop`; no canonical ack to history.

### 8.4 Phase 4 — Deliberate-regression confirmations + closure narrative (~0.5 hours)

4 deliberate-regression confirmations (each: induce → corresponding test fails as predicted → revert → full-suite green):

- (a) Drop `VISITOR_ALERT` from `_ONE_SHOT_NUDGE_TYPES` exemption (i.e., revert D1) → Test 2 fails (nudge=no after first call) + Test 14 fails (persistence broken).
- (b) Revert D2 fallback branch in `build_shared_context_block` → Test 4 fails + Test 15 fails (no widening).
- (c) Revert D3 `await` → `create_task` → Test 6 AST fails + Test 7 behavioral fails (canonical ack reads stale name).
- (d) Drop FABRICATED ABSENCE bullet → Test 12 fails.

### 8.5 Total effort

**~9 hours = 1.5 days.** Matches Phase 0 §6.1 forecast (1.5-2 days). 16 tests collected (suite 2404 → 2420).

---

## 9. Risk + mitigation

### 9.1 Risk — Phase 1 D2 widening misfires on too many turns

**Concern**: every single-person turn now queries `get_recent_audience_rooms`. Cost = one SQLite query per turn for the lookup (~1-5ms) + N queries per matched room. For active owners with many recent multi-person rooms, this could add ~10-50ms per turn.

**Mitigation**:
- `get_recent_audience_rooms` LIMIT 5 caps the query count
- 24h window naturally bounds the recent room set
- Phase 3 behavioral test #15 measures latency; flag if p95 > 100ms
- If post-canary cost is too high, follow-up adds a session-scoped cache (compute once per session, reuse for ≤30 min)

### 9.2 Risk — Phase 1 D1 nudge-keeps-coming after stale relevance

**Concern**: Lexi visits Monday morning. Owner is busy all day; doesn't ask. Lexi visits AGAIN Monday evening (new visit). Owner returns Tuesday morning — TWO visitor alerts pending. Nudge surfaces both.

**Mitigation**:
- Bug-Q-equivalent dedup at queue time: `_run_visitor_alert` already calls `nudge_exists(bf_id, "VISITOR_ALERT", person_id)` (line 7129) before queuing → second alert for same pid is suppressed.
- For DIFFERENT pids (Lexi + Wasim both visit on the same day), both alerts persist — correct behavior, owner needs both.
- Re-canary observation: if multiple-visit-day-stale-alert proves jarring, follow-up adds time-decay-prioritization.

### 9.3 Risk — Phase 1 D2 widening reveals D-A → D2 boundary ambiguity

**Concern**: D-A was scoped to "live multi-person room"; D2 widens to "recent audience match." Is D2 logically D-A or a sibling? Plan v1 framing: D2 is a SIBLING fallback path to D-A's fast path. Same code (`build_shared_context_block`), same retrieval function (`get_recent_room_conversation`), different gate semantic.

**Mitigation**:
- Closure narrative explicitly documents D2 as "D-A widening, not D-F" — preserve the D-A spec's lineage.
- Test #4 + #5 both reference D-A semantic to keep the relationship visible.

### 9.4 Risk — Phase 2 D4 KNOWN SPEAKER IDENTITY block adds prompt-cache invalidation

**Concern**: Adding a new block to `_build_system_prompt` may invalidate Together.ai's prompt prefix cache. The cache hash depends on byte-identical prefix; per Wave 4 Item 16 (prompt caching architecture), Section 1 (PURE-STATIC) and Section 2 (SESSION-STABLE) are cache anchors.

**Mitigation**:
- The new block renders person_name + person_type interpolation. These are SESSION-STABLE (don't change mid-session). Goes in Section 2.
- Verify Section 2 prompt hash via existing tests in `tests/test_prompt_caching.py` — the new block should land in Section 2 boundaries, not Section 1.
- Plan v2 may add a precision item if the hash test surfaces drift.

### 9.5 Risk — Phase 3 E2E test fragility

**Concern**: behavioral integration tests with seeded conversation_log + cross-session retrieval are stateful and prone to fixture brittleness.

**Mitigation**:
- Reuse existing fixture builders from `tests/fixtures/event_log_fixtures.py` (P0.0.7) where applicable
- Phase 3 tests use direct-seed pattern (per P0.S7.2 §4 audit option) rather than full session-lifecycle replay
- AST source-inspection covers the structural invariants (Phase 1 + 2); E2E only verifies semantic integration

---

## 10. Discipline-count predictions on P0.S7.5 closure

| Discipline | Pre-P0.S7.5 | Post-closure |
|---|---|---|
| Spec-first review cycle | 14-for-14 | **15-for-15** ✓ |
| Sub-pattern A (`### Phase-0-catches-wrong-premise`) | 5 instances | **stays at 5** (partial-falsification, not wholesale) |
| Tripwires-must-match-deferral-surface | 4-for-4 | stays **4-for-4** |
| Developer-improves-on-spec | 6-for-6 | stays **6-for-6** unless code phase surfaces a mechanism improvement |
| Induction-surfaces-invariant-gaps | 7-for-7 | stays **7-for-7** unless Phase 4 surfaces real gap |
| Canary-finding tracker | 2 instances | **3rd instance** (P0.S7.5 is canary-surfaced) |
| Canary-gate override (informal) | 1 instance | stays at **1 instance** |
| Scope-expansion-via-Phase-0 (informal) | 1 instance | stays at **1 instance** |
| Deferral-rationale-expires-when-downstream-ships (informal) | 1 instance | stays at **1 instance** |
| Two-stage-canary-gated-cleanup (informal) | 2 instances | stays at **2 instances** (P0.S7.5 single-stage) |
| Auditor-Q5-estimates-trail-grep (architect-memory) | 3 instances | **4th instance** — first ON-TARGET estimate (auditor 12-19, actual 16) |
| Partial-falsification-tentative (architect-memory only) | 1 instance | **2nd instance** — re-evaluate framing crispness |

---

## 11. Plan v1 → Plan v2 anticipated precision items

Per auditor's Phase 0 verdict: "Plan v2 (if precision items surface, likely 2-3 at this scope)". Architect anticipates:

1. **D2 §4.4 query batching precision** — Plan v1 sketches a loop over `recent_room_ids` calling `get_recent_room_conversation` per room. Plan v2 may prefer a SINGLE unified query that joins room IDs + filters in one round-trip. Performance precision item.

2. **D3 §5.4 error-handling precision** — Plan v1 broadens the try/except to `Exception` (vs the original `RuntimeError`). Auditor may want a tighter exception class (e.g., specifically catch `asyncio.CancelledError` separately, OR don't catch at all and let the timeout dispatcher handle).

3. **D4 §6.3 KNOWN SPEAKER IDENTITY block content** — Plan v1 specifies contract; developer writes exact wording. Auditor may want explicit examples (verbatim like SYSTEM IDENTITY block §3.) or may want the block to also surface session-history (e.g., "last 3 things they said").

4. **Phase 3 §8.3 E2E test fixture** — Plan v1 lists 3 E2E tests. Auditor may want fixture builders (`build_visitor_session_e2e`, `build_owner_returns_e2e`) standardized in `tests/fixtures/` rather than ad-hoc per-test setup.

None of these are blockers; Plan v2 anticipated to be 1-2 page refinement.

---

## 12. Reference documents

- `tests/p0_s7_5_audit.md` — Phase 0 audit (APPROVED 2026-05-19 with 6 adjudications)
- `tests/p0_s7_de_audit.md` + closure — D-E reference (1st partial-falsification instance)
- `tests/p0_s7_dd_audit.md` + closure — D-D reference (sub-pattern A 5th instance + doctrine elevation)
- `tests/p0_s7_dc_audit.md` + closure — D-C Stage 1 reference (two-stage pattern 1st instance)
- `tests/p0_s7_db_audit.md` + closure — D-B Kuzu v3 reference
- `tests/p0_s7_audit.md` + closure — D-A SHARED CONTEXT reference (D2 widens this surface)
- `CLAUDE.md` `### Phase-0-catches-wrong-premise` doctrine
- **Canary terminal_output files (2026-05-19)** — primary evidence:
  - `terminal_output_2026-05-19_205906.md` — Jagan alone (~30 turns)
  - `terminal_output_2026-05-19_211154.md` — Lexi visitor session
  - `terminal_output.md` — Jagan returns; canary failure at turn 79
- `core/brain.py:199-236` — update_person_name description (D4 EDIT SITE 1)
- `core/brain.py:2013-2049` — format_system_identity_block (D4 TEMPLATE for parallel helper)
- `core/brain.py:2222-2311` — HONESTY POLICY block (D5 EDIT SITE)
- `core/brain.py:2545-2664` — VISITOR CONTEXT block (already correct; downstream of D1)
- `core/brain_agent.py:7075-7190` — `_run_visitor_alert` (already correct; queues nudge with markers)
- `core/brain_agent.py:8342-8363` — `PromptPrefAgent.get_prompt_addendum` (D1 PRIMARY EDIT SITE)
- `core/brain_agent.py:2934-2952` — `get_pending_nudges` (returns `nudge_type` ✓ in dict shape)
- `core/brain_agent.py:3063-3068` — `mark_nudge_injected` (write site; unchanged)
- `core/db.py:1296-1371` — `get_recent_room_conversation` (D-A; reused by D2)
- `core/db.py` (new) — `get_recent_audience_rooms` (D2 NEW HELPER)
- `core/room_orchestrator.py:231-310` — `build_shared_context_block` (D2 PRIMARY EDIT SITE)
- `core/room_orchestrator.py:261-264` — narrow gate (D2 widening site)
- `core/session_state.py:317-321` — `SessionStore.rename` async (D3 awaitable)
- `pipeline.py:3439` — `_handle_update_person_name` async def (D3 — can await directly)
- `pipeline.py:3766-3770` — rename create_task site (D3 PRIMARY EDIT SITE)
- `pipeline.py:5777-5781` — canonical ack template (D3 BENEFICIARY, no edit)
- Memory: `feedback_spec_time_grep_verification.md` (4 instances; two-pass discipline) — Pass 1 at §2
- Memory: `feedback_ast_forward_property_tests.md` (3 instances) — workhorse pair applied at §8
- Memory: `feedback_auditor_q5_estimates_trail_grep.md` (3 → 4 instances at closure; first ON-TARGET)
- Memory: `feedback_partial_falsification_tentative.md` (1 → 2 instances at this cycle)

---

**Standing by for auditor review of Plan v1. Anticipated precision items per §11.**

Plan v1 forecast: 16 tests (Phase 1 +5, Phase 2 +8, Phase 3 +3). Suite delta: **2404 → 2420 (+16)**. Total effort: ~1.5 days. Bundled-queue RE-CANARY runs IMMEDIATELY on closure.
