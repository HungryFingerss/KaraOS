# P0.S7.1 — SHARED CONTEXT canary runbook

**Date:** 2026-05-18
**Audience:** Jagan, after developer ships P0.S7.1.
**Purpose:** Validate that `<<<SHARED CONTEXT>>>` block actually renders in real multi-person sessions, using the new observability surface from P0.S7.1.

**Gates:**
- P0.S7.1 spec at `tests/p0_s7_1_spec.md`
- Architect verifies from logs after canary ends → confirms D-A's SHARED CONTEXT works correctly → unblocks D-C cleanup planning.

---

## 1. Pre-flight checklist

Before starting the canary session:

1. Confirm P0.S7.1 implementation merged and tests green:
   ```
   pytest -q tests/test_p0_s7_1_observability.py
   ```
   Expected: 3 logical tests pass (~6 collected).

2. Confirm the prior session's `terminal_output.md` is archived (it should auto-archive on next boot). If `terminal_output.md` already exists from a prior session, just start the system — boot will rename it.

3. Camera + mic working; pyannote model loaded (HF_TOKEN present in `.env`); cloud LLM key (`TOGETHER_API_KEY`) valid.

---

## 2. Canary scenario (~5-10 minutes)

The scenario exercises all 6 SHARED CONTEXT outcome paths so the canary log carries observable evidence for each.

### 2.1 Phase A — single-person warmup (~2 min)

1. Boot the system: `python pipeline.py`.
2. Sit alone in front of camera. Wait for greeting.
3. Have 2-3 normal turns (e.g., "How was your day?" → response → "Tell me about my schedule" → response).

**What this exercises:**
- Outcome B (single_person gate) on every turn — SHARED CONTEXT should NOT render
- Existing room block + scene block (baseline)

### 2.2 Phase B — bring in a second person (~3 min)

1. Have a second person (real or ElevenLabs / phone playback) join the camera frame AND speak.
2. Recommended scripts for the 2nd speaker:
   - First utterance: "Hi everyone, I just came in" (~1.5s; long enough to avoid short_hard band)
   - Second utterance: "What were you two talking about?" (the trigger — should pull SHARED CONTEXT)
   - Third utterance: A topic-shift like "I was thinking about going for coffee tomorrow"

**What this exercises:**
- Outcome B → Outcome F transition (single_person → render path)
- Multi-person room: SHARED CONTEXT block SHOULD render starting from the 2nd speaker's 2nd turn

### 2.3 Phase C — returning conversation (~2 min)

1. Have the original speaker (you) respond to something the 2nd speaker said.
2. One or two more cross-references in conversation — e.g., "Going for coffee sounds nice, where to?"

**What this exercises:**
- SHARED CONTEXT continues to render in multi-person room
- Brain behavior: does it weave in earlier turns from the room context?

### 2.4 Phase D — session end (~30s)

1. The 2nd person leaves (camera + mic) — wait for their voice-only session to time out (~30s).
2. After the 2nd person's session expires, have one more solo turn from you.

**What this exercises:**
- Outcome B (single_person) returns after multi-person ends
- Confirms gate transitions cleanly back to single-person

### 2.5 Phase E — graceful shutdown

1. Ctrl+C the pipeline cleanly (single press; wait for graceful shutdown).
2. Next boot will auto-archive `terminal_output.md` to a timestamped file.

---

## 3. Post-canary verification (grep commands)

After Phase E, the prior session's log is archived. Run these greps to verify each outcome path was exercised:

```bash
# A. SharedContext disabled (should be 0 unless flag flipped manually)
grep -c "\[SharedContext\] gate=flag_off" terminal_output_*.md

# B. Single-person gate (should be > 0; fires on every Phase A turn)
grep -c "\[SharedContext\] gate=single_person" terminal_output_*.md

# C. No room_session_id (should be 0 unless boot-race surfaced)
grep -c "\[SharedContext\] gate=no_room_session_id" terminal_output_*.md

# D. Disputed caller (should be 0 unless a dispute fired during canary)
grep -c "\[SharedContext\] gate=disputed" terminal_output_*.md

# E. Multi-person room but empty result (should be > 0 on the 2nd person's FIRST turn — no prior persisted turns scoped to the new audience)
grep -c "\[SharedContext\] .* rows=0 → skip" terminal_output_*.md

# F. Block rendered (THE LOAD-BEARING GATE — should be > 0 on the 2nd person's 2nd+ turns and on returning speaker's turns)
grep -c "rendered" terminal_output_*.md
```

Also verify the `[Brain] Context:` summary extension landed:

```bash
# Should be > 0 and appear on every conversation turn
grep -c "\[Brain\] Context:.*shared_context=" terminal_output_*.md
```

---

## 4. Pass / fail criteria

**PASS conditions (all must hold):**

1. **Outcome F (rendered) fires ≥ 1 time** — confirms SHARED CONTEXT actually rendered in a multi-person turn. (THE HEADLINE CRITERION.)
2. **Outcome B (single_person) fires ≥ 2 times** in Phase A + Phase D — confirms gate works for single-person.
3. **Outcome E (rows=0) and Outcome F (rendered) BOTH fire** during Phase B — confirms transition from "empty room history" → "non-empty room history" surfaces correctly.
4. **`shared_context=<N>` field present in every `[Brain] Context:` line** — confirms summary extension landed.
5. **No `[SharedContext] gate=no_room_session_id` lines** — would indicate boot-race or session-state bug.

**FAIL conditions (any one triggers diagnosis):**

1. **Outcome F never fires** even though canary ran 2+ multi-person turns — D-A block has a bug. Diagnose before D-C.
2. **`shared_context=0` on every multi-person turn** — block returns None when it shouldn't. Diagnose.
3. **`[SharedContext] gate=no_room_session_id` fires repeatedly** — room minting bug.
4. **Brain behavior: explicit "you [to None]" anywhere in TTS** — schema-gap `addressed_to=None` exposed as load-bearing; need schema migration follow-up.
5. **Suite breaks at any point** — green-suite invariant violated.

---

## 5. What to report back

After the canary:

1. **Paste the 7 grep counts above.**
2. **Subjective: did the brain weave in cross-person context naturally?** (e.g., on the returning speaker's turn after multi-person, did the brain reference the earlier conversation?)
3. **Any unexpected behavior** — errors, hangs, weird phrasings.
4. **Confirm clean Ctrl+C shutdown** (so archive ran cleanly).

Architect will verify from logs and pronounce D-A truly validated → D-C planning unblocks.

---

## 6. Failure escalation

If FAIL condition #1 fires (Outcome F never fires in a multi-person turn):

- Architect drills into `_build_shared_context_block` execution path.
- Likely causes: (a) snapshot-vs-session-open race on first multi-person turn (we saw evidence of this in the 2026-05-18 canary at line 185); (b) `is_disputed_fn` accidentally returning True for non-disputed session (rare); (c) `get_recent_room_conversation` returning empty due to audience filter bug.
- Resolution: depends on root cause; may need P0.S7.2 (race-condition fix) or refinement to gate (2) semantic (use `_active_room_participants` count instead of `_active_sessions`).

If FAIL condition #4 fires (`you [to None]` audible):

- Schedule the `addressed_to` schema migration follow-up; this becomes a real blocker for D-C.
- Architect drafts the migration spec.

---

## 7. Reference documents

- `tests/p0_s7_audit.md` — Phase 0 audit
- `tests/p0_s7_plan_v2.md` — Plan v2 (D-A code contract)
- `tests/p0_s7_1_spec.md` — P0.S7.1 observability spec
- `terminal_output_2026-05-18_*.md` — prior canary log (no observability; this canary fills the gap)
