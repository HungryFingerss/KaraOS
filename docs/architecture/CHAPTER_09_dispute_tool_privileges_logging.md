> **CHAPTER 09 — Dispute + Tool Privileges + Logging** | Sourced from `everything_about_system.md` §100-118 (verbatim mechanical extraction per Plan v2 §1.6 section-number stability invariant).

---

## 100. Dream Loop — Memory Consolidation

### 100.1 Purpose

During idle periods, do the "memory gardening" that would be too expensive per-turn: decay, prune, normalise, reconcile.

### 100.2 Triggers

Two paths:
- **Idle** — no active sessions for `DREAM_IDLE_MINUTES=5`, and `DREAM_COOLDOWN=3600s` since last dream.
- **Force** — busy system with no idle window; `DREAM_MAX_INTERVAL=10800s` force-fire even during active session.

### 100.3 Cycle operations

1. **Decay** — Apply `eff_conf = stored_conf × exp(-DECAY_LAMBDA × days_since_captured)` to every knowledge row.
2. **Prune** — If effective confidence drops below `DREAM_PRUNE_FLOOR=0.15`, invalidate the row.
3. **Schema normalisation** — SchemaNormAgent clusters attribute synonyms (≥ SCHEMA_NORM_THRESHOLD=0.97) and auto-merges.
4. **Row caps** — Enforce KNOWLEDGE_MAX_ROWS, PRESENCE_MAX_ROWS, EPISODE_MAX_ROWS, SOCIAL_MENTIONS_MAX_ROWS, AGENT_LOG_MAX_ROWS via oldest-first deletion.
5. **Age-based pruning** — WATCHDOG_MAX_AGE_DAYS, AGENT_LOG_MAX_AGE_DAYS, PATTERN_Q_MAX_AGE_DAYS.
6. **Stranger TTL** — delete strangers unseen for `STRANGER_TTL_DAYS=7`.
7. **Stranger voice TTL** — delete thin stranger voice profiles unupdated for `STRANGER_VOICE_TTL_DAYS=3`. Cache evicted FIRST (Finding J ordering).
8. **Voice gallery reconciliation (Obs 1)** — compare `_voice_gallery_sizes` to `db.load_voice_profile_sizes()`. Divergence → full reload.
9. **Silent observations retention** — `SILENT_OBS_RETENTION_DAYS=45`.

### 100.4 Log format

```
[Dream] Force trigger — system has been busy, running dream during active session
[Dream] Starting consolidation cycle (idle=0.0min, force=True)
[Dream] Consolidation started — N person(s) in DB
[Dream] Consolidated — N pruned, M decayed, K stable
[Dream] Voice gallery cache reconciled: N pid(s) out of sync
```

### 100.5 Cost

Typical cycle: ~500ms on a 100-person DB. Negligible at our scale.

---
---

# Part XV — Dispute State Machine

## 101. Origin — The Uncle-False-Match Incident

In an earlier session, Jagan's uncle visited. The face recognition matched him to Jagan at score ~0.35 (above threshold of 0.18 at the time). The system greeted him as Jagan. He didn't correct it. A few turns in, the brain extracted facts attributing the uncle's statements to Jagan.

By the time the mistake was caught, Jagan's knowledge graph was polluted with uncle's facts. Recovery required factory reset (there was no partial-rollback mechanism).

The incident exposed two gaps:
1. **Recognition was too permissive.** Fixed by raising thresholds and adding the centroid gate.
2. **There was no mechanism for the speaker to say "no, I'm not that person."** The LLM was told the speaker was Jagan; it had no way to express doubt.

The dispute state machine closes the second gap.

## 102. Trigger Paths

> **Architectural note (2026-05-15).** Pre-P0.7, every dispute-trigger site directly wrote `_active_sessions[pid]["person_type"] = "disputed"` and the three companion fields (`dispute_set_at`, `prior_person_type`, `disputed_claimed_name`). Different sites set different subsets — `prior_person_type` was missed at one site, `dispute_set_at` was missed at another, and auto-clear sometimes restored to `"known"` instead of the original type. P0.7 routed all three operations through the named transition `transition_to_disputed(pid, claimed_name, reason, now)`. The transition captures `prior_person_type` atomically with the other three fields; restore via `clear_dispute(pid, now)` reads `prior_person_type` and fail-closes to `"stranger"` per P0.2 if missing.

A session enters disputed state via one of these paths:

1. **`report_identity_mismatch` tool** (Session 51 #2B). LLM flags that the speaker contradicts the sensor. The `_handle_report_identity_mismatch` handler (Part XLI §272) calls `await _session_store.transition_to_disputed(pid, claimed_name=None, reason="report_identity_mismatch", now=time.time())`.
2. **`update_person_name` on a known session** (Session 54/55). A speaker whose session is `known` or `best_friend` says they are a different person. Instead of renaming (which would corrupt the real person's row), `_handle_update_person_name` calls `transition_to_disputed(pid, claimed_name=proposed_name, reason="rename_on_known", now=...)`.
3. **Auto-dispute** (rare). An explicit code path for internal consistency checks. Calls the same `transition_to_disputed` method.

The single named transition is the only writer for the four fields. Future paths that want to enter dispute state must call this method; the AST scan in `tests/test_no_raw_disputed_comparisons.py` (P0.1, Part XXXVI §234) rejects any raw `person_type = "disputed"` write outside the helper.

## 103. `<<<IDENTITY DISPUTED>>>` Block

```
<<<IDENTITY DISPUTED>>>
  The speaker has contradicted sensor evidence about who they are.
  Treat them as unknown. Do not reference stored facts about them by
  any name. Use update_person_name if they give a valid clean name.
<<<END>>>
```

Injected in `_build_system_prompt` whenever the session's snapshot satisfies `_is_disputed(snapshot)`. This instructs the brain to behave as if the speaker is a stranger, regardless of the face or voice match.

## 104. `_disputed_persons` Set

`BrainOrchestrator._disputed_persons: set[str]` — pids currently in dispute. Used by the orchestrator to gate agent work:

- `_process_turn` first checks this set; disputed → skip triage/extraction.
- `notify_session_end` skips all 6 session-end helpers when disputed.

`mark_disputed(pid)` and `clear_disputed(pid)` are the orchestrator-side API; the pipeline calls them from inside the corresponding `transition_to_disputed` / `clear_dispute` paths in `SessionStore`.

## 105. Session-End and Conversation-Log Gating

Session 53 Findings A and B made the gating airtight:

- **A (session-end gate):** `notify_session_end` checks `_disputed_persons` and skips PromptPrefAgent, InsightAgent, HouseholdAgent, NudgeAgent visitor alert, and SocialGraphAgent.
- **B (conversation_log gate):** `conversation_turn` and `_kairos_tick` check `_is_disputed(_session_store.peek_snapshot(pid))` before calling `db.log_turn`. Disputed-session turns stay in-memory only; never touch the DB.

This means a dispute leaves no persistent trace beyond the watchdog alert. If it resolves cleanly (via rename), the clean pid's knowledge is unaffected.

The `_is_disputed()` helper is the canonical predicate. Every check in the codebase routes through it (enforced by `tests/test_no_raw_disputed_comparisons.py` — P0.1, Part XXXVI §234) so future changes to dispute state representation (e.g. moving from string to enum) don't have to scatter through every call site.

## 106. Force-Close Timeout

`DISPUTE_MAX_DURATION=180s`. After 3 minutes of dispute with no resolution, `_expire_stale_sessions` force-closes the session. Session 53 Finding C added this because vision can keep matching the wrong person, preventing natural expiry via FACE_LOSS_GRACE.

Session 54 Finding K added a lazy anchor that became unnecessary after P0.7: if `dispute_set_at` is missing (future code path forgot to set it), the old behaviour was to anchor it on first observation. P0.7's `transition_to_disputed` writes `dispute_set_at` atomically with the other three fields, so the field is guaranteed present whenever `person_type == "disputed"`. The lazy-anchor fallback was kept as defense-in-depth but is now unreachable in practice.

## 107. Dispute-Rename Burst Watchdog

Session 57 N3. When disputed-rename attempts accumulate, the rename-block path inside `_handle_update_person_name` calls the named transitions:

```python
# In the disputed rename-block path (P0.7 — named transitions):
await _session_store.increment_block_count(pid)
snap = _session_store.peek_snapshot(pid)
if (snap.disputed_block_count >= DISPUTE_RENAME_BLOCK_THRESHOLD
    and not snap.disputed_block_alerted):
    await _session_store.mark_block_alerted(pid)
    _brain_orchestrator.report_dispute_rename_burst(
        pid,
        victim_name=snap.person_name,
        victim_type=snap.prior_person_type,        # P0.2 fail-closed default
        claimed_name=args.get("name"),
        count=snap.disputed_block_count,
        dispute_ts=snap.dispute_set_at,
    )
```

`increment_block_count` and `mark_block_alerted` are dedicated transitions — both idempotent — that replaced direct dict mutation in P0.7.3. The `mark_block_alerted` transition is idempotent at the field level (sets `disputed_block_alerted=True`), but it's gated by the `if not snap.disputed_block_alerted` predicate so the actual `report_dispute_rename_burst` call fires exactly once per dispute episode.

Severity: `critical` if the victim's prior type was `best_friend` (owner impersonation); `warning` otherwise. Alert stored in `watchdog_alerts` for dashboard surfacing.

---
---

# Part XVI — Tool System

## 108. `TOOL_PRIVILEGES` Table

```python
TOOL_PRIVILEGES: dict[str, frozenset[str]] = {
    "shutdown":                 frozenset({"best_friend"}),
    "update_system_name":       frozenset({"best_friend"}),
    "update_person_name":       frozenset({"stranger", "known", "best_friend", "disputed"}),
    "report_identity_mismatch": frozenset({"stranger", "known", "best_friend", "disputed"}),
    "search_web":               frozenset({"stranger", "known", "best_friend"}),
    "search_memory":            frozenset({"known", "best_friend"}),
}
```

Maps tool name → set of person_types that can invoke it. Single table; grep-able; edit here to adjust policy.

## 109. `_tool_allowed` Fail-Closed

```python
def _tool_allowed(tool_name: str, caller_type: str) -> bool:
    allowed_types = TOOL_PRIVILEGES.get(tool_name)
    if allowed_types is None:
        # Tools not in the table are BLOCKED, not unrestricted. Fail-closed.
        return False
    return caller_type in allowed_types
```

An unregistered tool is blocked. This means adding a new tool requires also adding its privilege row — the startup assertion (§110) enforces.

## 110. Startup Assertion

```python
# In run():
assert set(t["function"]["name"] for t in brain.TOOLS) <= set(TOOL_PRIVILEGES.keys()), (
    "Every tool in brain.TOOLS must have a TOOL_PRIVILEGES row"
)
```

Fires on startup before any model loads. If you add a tool and forget the privilege, the system refuses to start. Makes it structurally impossible to ship an un-gated tool.

## 111. `<<<TOOL ACCESS>>>` Block

See §72.3. Injected into every system prompt so the brain knows upfront what it can call. Before this block (Session 61), the brain would sometimes spend 5 turns retrying a blocked call because it didn't know the block existed.

## 112. History Override Semantics

`HISTORY_OVERRIDE_TOOLS = frozenset({"update_system_name", "update_person_name"})`. When these fire:

1. `stop_audio()` cuts the wrong streaming text.
2. Canonical acknowledgment replaces the LLM text in `history`.
3. TTS speaks the canonical acknowledgment.

Prevents the L1-L4 "infinite repeat" bug from Session 25 where wrong streaming text would poison history and trigger the same tool call next turn.

## 113. Tool Repeat Guard

```python
TOOL_REPEAT_MAX_CONSECUTIVE = 2
```

If the same `(tool_name, args_hash)` has fired 2 consecutive times on the same session, the 3rd attempt aborts with a warning. Prevents infinite loops where the LLM keeps calling the same tool with the same args (Session 25 L3).

---
---

# Part XVII — Observability

## 114. `log_utils` — Single Source of Truth

```python
# core/log_utils.py
def _now_log_ts() -> str:
    raw = _dt.datetime.now().strftime(LOG_TIME_FORMAT)
    if LOG_TIME_FORMAT.endswith("%f") and len(raw) >= 3:
        return raw[:-3]   # trim microseconds to milliseconds
    return raw

def _log_trunc(s: str, limit: int | None = None) -> str:
    effective = LOG_STT_MAX_CHARS if limit is None else limit
    if not effective or len(s) <= effective:
        return s
    return s[:effective] + "…"
```

One place defines log time format. Grep for `_now_log_ts` to find every timestamped log site. No ad-hoc `datetime.now().strftime()` anywhere else (Session 47 Finding K verified).

## 115. Seven Timestamped Categories (now Ten with Observability 2.0)

- `[STT] HH:MM:SS.mmm (Nms) 'text'`
- `[Audio] TTS HH:MM:SS.mmm: 'text'`
- `[Voice] HH:MM:SS.mmm Routing: ...` — includes P3.23 tier diagnostics
- `[Brain] HH:MM:SS.mmm Tool: ...`
- `[Pipeline] Turn start HH:MM:SS.mmm: ...` / `Turn end ...` / `Turn addressed: X (source)`
- `[BrainAgent] HH:MM:SS.mmm Triage: ...` / `Extracted ...`
- `[Intent] tools=[...] classified=X value='Y' conf=0.NN reason=...` — Phase 1 classifier sidecar
- `[Room] New room session: ...` / `Ended: ...` / `Participant added: ...` / `Synthesis complete: ...`
- `[Anti-spoof] summary over last N frames: ...`
- `[ContradictionAgent] {SAFETY_PATTERN_MATCH}: preserve, no replace` — Session 105 Bug N

Non-timestamped logs (e.g., `[Vision] Jagan` heartbeat) are intentionally untimestamped because they fire too frequently and time-stamping them would bury signal.

For the full specification of each category's format, see **Part XXVIII — Observability 2.0**.

## 116. STT Elapsed Ms

`transcribe()` stores elapsed into module-level global `_last_stt_elapsed_ms`. Pipeline reads and re-logs on turn-start line. Single measurement, two log surfaces.

```python
[STT] 01:20:41.223 (635ms) 'Hi there'
[Pipeline] Turn start 01:21:21.296: Jagan — 'Yeah, how about you? What are you thinking?'
```

## 117. Rolling Anti-Spoof Summary

`LOG_ANTISPOOF_SUMMARY=True`, `LOG_ANTISPOOF_SUMMARY_INTERVAL=100`. Every 100 calls, emit:

```
[Anti-spoof] summary over last 100 frames: min=0.93 mean=0.97 max=1.00 rejects=0 thr=0.50
```

Passive drift detection. If camera or lighting degrades over time, mean drops and operator notices without reading every frame's probs.

`LOG_ANTISPOOF_PROBS=False` by default — flip ON for acute debugging.

## 118. Scene Heartbeat Dedup

`[Vision]` heartbeat only prints on change. A stationary scene doesn't spam.

```python
if _vis_report_now != _last_vision_report_str:
    print(f"[Vision] {_vis_report_now}")
    _last_vision_report_str = _vis_report_now
```

Session 38 Issue #6.

---
---

# Part XVIII — Persistence

