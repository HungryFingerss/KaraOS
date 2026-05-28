# P0.S10 + P0.S11 + P0.S12 — bundled Phase 0 audit (canary Day 1 findings)

**Canary trigger:** 2026-05-27 live Day-1 session against terminal_output_2026-05-27_115642.md. Three independent bugs surfaced; bundled because (a) they all originated in the SAME canary run, (b) they're scoped tight enough each that closing them sequentially under strict mode in ~1-2 architect days is tractable, (c) the 2nd bundled-cycle precedent (P0.B5 closed 2026-05-21) is the canonical model for this shape.

**Bundle rationale (auditor): not P0.B5's "4 D-decisions across 4 subsystems in one cycle" pattern.** This is "3 independent specs documented in one Phase 0 artifact for auditor convenience, then shipped as 3 separate Plan v1 + closure cycles." Each spec gets its own Plan v1, its own closure-audit, its own coverage matrix update. The bundle is documentary, not architectural.

**Strict-mode discipline applied to each spec:** per-spec pre-mortem + multi-direction invariant trace + 11-gate quality checklist + cross-spec impact analysis + closure-audit scheduled. Per `feedback_strict_industry_standard_mode.md` §1.

**Canary source-of-truth:** `c:/Users/jagan/dog-ai/dog-ai/terminal_output_2026-05-27_115642.md` — lines referenced inline for each finding.

---

# P0.S10 — Brain + classifier misinterpret topic-denial as identity-denial

**Symptom (terminal_output:114-166):** User said `"who said I'm in office I don't have any job and I don't go to office"` (correction to brain's fabricated greeting "How's the office treating you?" at line 86). Brain emitted `report_identity_mismatch({'reason': 'speaker insists they are not working'})` at line 155. Intent classifier ratified at line 164: `classified=deny_identity value=None conf=0.95 reason='The user explicitly denies being in an office and having a job, which suggests t'`. Validator passed at line 165: `Tool: report_identity_mismatch allowed by intent gate — intent match`. Session entered disputed state at line 166.

**Phase 1 fact extraction got skipped** at lines 170-171: `Triage: SKIP turn 43 — identity disputed for jagan_3206e3`. Brain's response at line 169: `'Sorry, I missed that. Could you say it again?'` — the LLM hedge after dispute fires.

## §1.1 Grep-verified surfaces affected

**Layer 1 — LLM tool description** (`core/brain.py:455-498`, verified via grep `report_identity_mismatch`):

The tool description is already RICH. Contains explicit TRIGGER CHECKLIST (4 items), DO-NOT list (5 items), question-detection hint ("If the user is asking a question (contains 'who', 'what', 'did', etc.) it is almost certainly NOT an identity mismatch"). The LLM IGNORED these in this canary turn despite their explicit presence. **The description ISN'T the gap** — judgment failure under the existing description is.

**What the description DOES NOT explicitly cover:** topic-denial vs identity-denial distinction. The rule says "denying the sensor's identification of them" but doesn't have a concrete counter-example for the exact canary phrasing class — "I don't [do X that the system implied I do]" mapped to identity denial. The LLM extrapolated from "denies a topic the system asserted" → "denies the identity that asserted the topic" — a leap the description doesn't prevent.

**Layer 2 — Intent classifier prompt** (`core/brain.py:809` `deny_identity` definition + surrounding rules verified via grep):

Current definition (line 809-810):
```
deny_identity            — user denies the sensor-matched identity
                            ('I'm not Jagan', 'wrong person')
```

QUESTION-vs-ASSERTION rule (line 828-842) covers question-shaped non-assertions but explicitly NOT topic-assertion-vs-identity-assertion distinction. The closest counter-example is `"Are you sure I'm Jagan?"` → `casual_conversation` (doubt question), but no entry for `"I don't have a job"` (assertion denying topic, not identity).

**The gap is here.** Classifier had no anti-pattern guidance for "user denies a fact/activity/topic" → that's `personal_statement` (line 815), not `deny_identity`.

**Layer 3 — Server-side validator** (`pipeline.py:727-816` `_intent_allows`):

Validator passed because:
1. `TOOL_INTENT_MAP["report_identity_mismatch"] = ("deny_identity", None)` (`core/config.py:503`)
2. `turn_intent == required` ✓ (classifier said `deny_identity`)
3. `confidence >= INTENT_CONFIDENCE_MIN=0.75` ✓ (0.95)
4. `extracted_value` is None → grounding block at lines 773-794 SKIPS entirely
5. `elif arg_key and tool_args.get(arg_key)` at line 795 → `arg_key is None` → falls through
6. Returns `(True, "intent match")` at line 816

**The validator has NO grounding requirement for `report_identity_mismatch`** because the tool's only arg is `reason` (free-text rationale), not a structured identity field. This is the structural gap — the dual-gate has no third gate to catch LLM+classifier dual-failure on identity-mismatch.

## §1.2 D-decisions sketched

**D1 — Intent classifier prompt: explicit topic-denial-vs-identity-denial rule** (`core/brain.py::_INTENT_CLASSIFIER_SYSTEM` around line 838 — add ASSERTION-DOMAIN RULE block right after QUESTION-vs-ASSERTION RULE).

Rule body should name 3-4 counter-examples verbatim from the canary, plus generic phrasings:
- `"I don't have a job"` → `personal_statement` (denies activity-fact, NOT identity)
- `"I don't work at an office"` → `personal_statement`
- `"That's wrong, I never go to office"` → `personal_statement` (correction, NOT identity-denial)
- `"I'm not in office"` → `personal_statement` (topic-correction)
- vs `"I'm not Jagan"` → `deny_identity` (identity-claim denial)
- vs `"You have the wrong person"` → `deny_identity` (explicit mistaken-identity claim)

Distinguishing pattern: identity-denial REQUIRES the user to refer to themselves with an identity claim (their name, "I am", "I'm called", "you're talking to the wrong person"). Topic-denial denies a TOPIC the system asserted; it does NOT claim a different identity.

**D2 — Tool description: canary phrasing as explicit anti-example** (`core/brain.py:465-486` — extend the DO-NOT-call list).

Add to existing DO-NOT list:
- "Topic corrections — e.g. 'I don't have a job', 'I don't go to office', 'I'm not in school'. These deny FACTS the system asserted about the speaker, not the speaker's IDENTITY. Call NOTHING (let the brain respond conversationally to clarify the fact). Identity-denial requires the speaker to reject their NAME, not their activities or topics."

**D3 — Validator: identity-claim grounding gate for `report_identity_mismatch`** (`pipeline.py::_intent_allows` after the existing extracted_value/arg_key block ~line 815).

Add a tool-specific gate (similar to the existing `tool_name == "shutdown"` floor at line 768):

```python
if tool_name == "report_identity_mismatch":
    # Identity-denial structural gate: user_text MUST contain a
    # self-identity-rejection phrase. Defense-in-depth against
    # LLM+classifier dual-failure on topic-denial vs identity-denial.
    _IDENTITY_DENIAL_PATTERNS = (
        r"\b(?:i'?m|i am|i'?ve been|i was)\s+not\s+\w+",  # "I'm not Jagan"
        r"\bnot\s+(?:the|that)\s+(?:right|correct|same)\s+person\b",  # "not the right person"
        r"\bwrong\s+person\b",  # "you have the wrong person"
        r"\b(?:my name|i'?m called|call me)\s+\w+\b",  # "my name is X" (denial-by-correction)
        r"\bnot\s+who\s+you\s+think\b",  # "I'm not who you think"
    )
    _ut = _nfkc_lower(user_text)
    if not any(re.search(p, _ut) for p in _IDENTITY_DENIAL_PATTERNS):
        return (
            False,
            "report_identity_mismatch requires explicit identity-rejection phrase in user_text",
        )
```

Architect's lean: regex-based gate is cheap and unambiguous. Borderline cases (user says "It's not me" with no other context) fail-closed → user can re-state more explicitly. Cost of false-reject (annoying re-prompt) << cost of false-accept (Session 51 uncle-false-match class regression).

**Open Q for auditor — D3 patterns are an architect's first cut.** Should we (a) ship as-listed; (b) widen with additional phrases the auditor surfaces; (c) ship without D3 if D1+D2 are judged sufficient (lighter-weight cycle).

## §1.3 Anchor estimate (auditor Q5)

Mid-range: 8 anchors. Inclusive ±15% band: [6.8, 9.2].

Breakdown:
- D1: 2 anchors (prompt contains ASSERTION-DOMAIN RULE block + ≥3 verbatim counter-examples)
- D2: 1 anchor (tool description contains topic-correction anti-example)
- D3: 4 anchors (regex pattern presence + behavioral allow for "I'm not Jagan" + behavioral reject for "I don't have a job" + pattern coverage across 5 phrasings via parametrize)
- Cross-cutting: 1 anchor (golden_intent.jsonl: add canary's exact phrasing as `regression_session_canary_day1` row tagged with `expected_intent=personal_statement`)

## §1.4 Pre-mortem (3 ways this fix could fail)

1. **D1+D2 prompt tightening doesn't prevent LLM judgment failure** — the LLM ignored existing tool-description guidance in the canary. Adding more text to prompts is correlated-with-improvement but not deterministic. **Mitigation:** D3 structural gate is the load-bearing safety net; D1+D2 reduce surface but aren't relied on alone.
2. **D3 regex patterns reject legitimate identity-denials we didn't anticipate** — e.g. "You think I'm Jagan but I'm Rahul" might miss the pattern. **Mitigation:** include 5 patterns covering canonical shapes; ship with `_IDENTITY_DENIAL_PATTERNS` in `core/config.py` so future cycles can extend (same shape as `SYSTEM_NAME_ASSIGN_PATTERNS` from S73).
3. **Cascading effect: D3 blocks legitimate dispute resolution in some flow** — the `auto-confirm dispute` path or some other state-machine corner might rely on `report_identity_mismatch` firing on different shape. **Mitigation:** grep all `report_identity_mismatch` call sites + assert D3 is consistent with existing call sites in `tests/test_p0_s10_identity_mismatch_precision.py`.

## §1.5 Multi-direction invariant trace

- **Forward:** identity-denial requires identity-claim phrase → topic-corrections route to `personal_statement` → triage extracts the fact normally → session stays open → no dispute → user can correct topic naturally.
- **Reverse:** if extraction tries to write "user denies has-job=true", contradiction check fires (existing P0.4 + session 105 path) → handled correctly.
- **Cross-spec:** P0.S7.5.2 D2 (engagement gate) — no overlap; engagement gate is for voice-only stranger sessions. P0.B6 reconciler cascade — no overlap; reconciler is for routing, not intent. P0.S5 prompt injection — no overlap; wrap_user_input is upstream of the intent classifier.

## §1.6 Cross-spec impact

- **Touches:** `core/brain.py` (D1 + D2 prompt changes), `pipeline.py` (D3 validator), `core/config.py` (new `_IDENTITY_DENIAL_PATTERNS` constant), `tests/golden_intent.jsonl` (regression row).
- **Reads:** `core/config.py::TOOL_INTENT_MAP` (no change), `core/config.py::INTENT_CONFIDENCE_MIN` (no change), `core/brain.py::_INTENT_CLASSIFIER_SYSTEM` (extended, not replaced).
- **Doesn't touch:** session state machine, reconciler, voice gallery, FAISS, Kuzu, dashboard.
- **Test surfaces:** `tests/test_p0_s10_identity_mismatch_precision.py` NEW + `tests/test_intent_classifier.py` extended for D1 + `tests/test_intent_allows.py` extended for D3.

---

# P0.S11 — Factory reset path audit + standalone CLI tool

**Symptom (terminal_output:2-38):** User ran "factory reset" before canary Day 1 (per their own statement). At pipeline boot, line 3 shows `[Dashboard] First-launch auth URL written to faces/.dashboard_auth_url` — meaning `.dashboard_token` was MISSING (the only path that emits this log is `_ensure_dashboard_token` when token absent). But faces.db SURVIVED: line 8 reports `faces.db: ledger already versioned (10 row(s) present)`, line 10 `FAISS out of sync: index=0, valid_rows=7` (7 face embeddings in SQL), line 20 `Gallery loaded — 1 person(s) with voice profiles`, line 33 `Graph rebuilt from 49 SQLite rows`, line 38 `knowledge=38(0shadow)`.

The user said "factory reset done" but the DB state shows a PARTIAL reset — only `.dashboard_token` got wiped; faces.db + brain.db + voice gallery + Kuzu graph all survived. Line 54 confirms the recognition: `[Vision] Background: recognized Jagan (score=0.775)` — Jagan was in the gallery from a prior session.

## §2.1 Grep-verified facts

- **`tools/factory_reset.py` does NOT exist** (verified via `glob "**/factory_reset*.py"` returns no Python files). There's NO standalone CLI script for factory reset.
- **Two reset paths exist:**
  - `core/db.py::wipe_all()` (`core/db.py:1984-2063` verified via grep) — programmatic Python API; deletes faces.db + brain.db + FAISS + Kuzu + photos + IPC files. **Preserves `.dashboard_token` and `.dashboard_auth_url`** by design (P0.S2 invariant documented at lines 1991-1998).
  - `dog-ai-dashboard/app/api/factory-reset/route.ts` (verified via file read) — Next.js POST endpoint; either calls pipeline IPC (if pipeline live) or wipes files directly via Node.js (if pipeline offline). Also preserves `.dashboard_token`.
- **What the user likely did** (best inference from log signature): manually deleted `.dashboard_token` file expecting that to trigger a full reset. OR ran some command that only touched the dashboard token. The DB state proves the wipe_all() path did NOT execute.
- **CLAUDE.md mention of `tools/factory_reset.py`** (verified via grep) — the canary runbook at `tests/canary_week_2026-05-26.md:39` says `python tools/factory_reset.py` as an example. **This file doesn't exist.** The runbook references a tool we never built.

## §2.2 Root cause classification

This is **partially user error + partially tooling gap.** The user expected a tool that doesn't exist; the documentation referenced it; the actual reset paths exist but are either UI-driven (dashboard) or programmatic-only (Python API).

The fix is NOT "investigate what user did wrong" — it's "ship the missing tool + make documentation match reality + add observable confirmation log."

## §2.3 D-decisions sketched

**D1 — `tools/factory_reset.py` NEW standalone CLI script.**

Mirrors the existing tools/ scripts pattern (`tools/replay_session.py`, `tools/extract_tool_handler.py`). Imports `core.db.wipe_all` + calls it + prints summary.

Specific shape:
```python
"""Standalone factory reset CLI — wipes faces.db / brain.db / FAISS / Kuzu / photos.
Preserves .dashboard_token (P0.S2 invariant — re-issuing auth URL on every reset is hostile UX).
Mirrors `core.db.wipe_all()` semantics. Safe to run with pipeline OFFLINE only —
running while pipeline holds DB connections will fail at file-rename step.

Usage:
  python tools/factory_reset.py [--confirm] [--include-dashboard-token]

Without --confirm, prints what WOULD be deleted (dry-run).
"""
```

Add `--confirm` flag (default-deny, mirrors dashboard's `confirm=RESET` requirement) + `--include-dashboard-token` flag (extends scope beyond `wipe_all()` to also delete `.dashboard_token` for cases where the user explicitly wants a full re-init).

**D2 — Confirmation summary log in `wipe_all()` (`core/db.py:1984-2063`).**

Add a final log block after all deletions enumerating exactly what was deleted vs what was preserved:
```
[Reset] Summary:
  Deleted: faces.db, faces.db-shm, faces.db-wal, faiss.index, brain.db, brain.db-shm, brain.db-wal, brain_graph/, sim_session_state.json, N photos, M IPC files
  Preserved (P0.S2 invariant): .dashboard_token, .dashboard_auth_url
  Total bytes freed: X.X MB
```

Without this, the user has no visible signal that wipe_all() actually ran. The canary's failure would have been catchable IF the user had seen "Deleted: faces.db, brain.db, ..." in stdout.

**D3 — CLAUDE.md + runbook reference fix.**

Update `tests/canary_week_2026-05-26.md` pre-canary checklist (currently references `tools/factory_reset.py` which doesn't exist) — after D1 ships, the reference becomes correct. NO change to runbook IF we decide D1 is the only path forward.

## §2.4 Anchor estimate (auditor Q5)

Mid-range: 6 anchors. Inclusive ±15% band: [5.1, 6.9].

Breakdown:
- D1: 3 anchors (script exists + `--confirm` default-deny + `--include-dashboard-token` flag enumeration + dry-run path)
- D2: 2 anchors (summary log fires after wipe + names deleted files + names preserved files)
- D3: 1 anchor (canary runbook reference checks out post-D1)

## §2.5 Pre-mortem (3 ways this fix could fail)

1. **D1 script accidentally deletes `.dashboard_token` by default** — if `--include-dashboard-token` defaults True OR if the script's wipe_all call passes a flag that overrides. **Mitigation:** D1 default = `.dashboard_token` preserved (matches wipe_all); flag opt-in only.
2. **D1 runs while pipeline is live, hits file-locks, leaves partial wipe state** — Windows file locks on faces.db will fail mid-delete. **Mitigation:** D1 starts with a pipeline-liveness check (read `faces/state.json`, see if `updated_at` is within last 10s — same heuristic the dashboard endpoint uses); refuses to run if pipeline live with actionable error: "Pipeline appears to be running. Stop it first or use the dashboard's factory-reset endpoint."
3. **D2 summary log misleads operator** — claims success when some delete failed silently (existing `except Exception` pattern in wipe_all). **Mitigation:** D2 summary counts ACTUAL deletions (probe file existence post-call), not assumed; report partial-success state if any delete didn't complete.

## §2.6 Multi-direction invariant trace

- **Forward:** user runs `python tools/factory_reset.py --confirm` → pipeline-liveness check → wipe_all fires → summary log emits → user sees confirmation → next boot starts clean.
- **Reverse:** if wipe_all partial-fails (file lock), summary log reports partial state, user can investigate.
- **Cross-spec:** P0.S2 dashboard auth preservation invariant — D1 + D2 both PRESERVE `.dashboard_token` by default; only the explicit opt-in `--include-dashboard-token` flag bypasses. Matches existing P0.S2 architectural intent.

## §2.7 Cross-spec impact

- **Touches:** `tools/factory_reset.py` (NEW), `core/db.py::wipe_all()` (D2 summary log).
- **Reads:** `core/config.py::FACES_DIR`, `DB_PATH`, `BRAIN_DB_PATH`, etc. (no change).
- **Doesn't touch:** pipeline.py, dashboard, brain, vision, audio.
- **Test surfaces:** `tests/test_p0_s11_factory_reset_cli.py` NEW (3-4 anchors); existing wipe_all tests extended for D2 summary.

---

# P0.S12 — terminal_output.md PermissionError on multiprocessing.spawn re-import

**Symptom (terminal_output:37, 42, 47, 60, 120):** Repeated WARN every ~30s: `could not archive terminal_output.md (PermissionError: PermissionError(13, 'The process cannot access the file because it is being used by another process')). Continuing without archive — investigate which process is holding the file.`

This is NOT random noise. The pattern is `pipeline.py` is re-imported multiple times during a single run (heavy-worker subprocess spawn fires module-level code, including `_archive_terminal_output()` at line 81 of pipeline.py). The parent process holds `_LOG_FILE = open(_LOG_PATH, "w", ...)` (line 83-88). The child subprocess tries to rename the file → Windows raises PermissionError 13 because the parent process has an exclusive file handle.

## §3.1 Grep-verified call chain

- **`_archive_terminal_output()` called from 2 sites only** (`pipeline.py:81` module-level + `pipeline.py:118` from `_check_terminal_output_size_cap`).
- **Size-cap call site fires only when `size_mb >= TERMINAL_OUTPUT_SIZE_CAP_MB=100`** (`pipeline.py:109`). Canary log is ~300 lines, well under 100 MB. So size-cap is NOT firing here.
- **The repeated PermissionError MUST be coming from the module-level call at line 81.** Confirmed: `mp.get_context("spawn")` is used by `core/heavy_worker.py` (verified via grep `mp.get_context("spawn")`). On Windows, spawn-mode subprocess RE-IMPORTS the main module. Every spawn → line 81 fires → parent holds file → PermissionError.
- **Boot success line 2** (`[Pipeline] Prior session log archived → terminal_output_2026-05-26_124202.md`) fires from `pipeline.py:204` ONLY when `_archived_log is not None`. So the PARENT process's archive succeeded at line 81 (the file existed from the prior session, parent grabbed it, no contention). Subsequent CHILD process archive attempts fail because the parent already opened the new (fresh) `terminal_output.md` at line 83.

## §3.2 D-decisions sketched

**D1 — Gate module-level archive + log-file-open behind `if __name__ == "__main__":` block.**

Move `pipeline.py:81-88` (the `_archive_terminal_output()` call + `_LOG_FILE = open(...)`) AND `pipeline.py:200-204` (the success-log print) inside a `__main__` guard. Subprocess re-imports will skip the archive call entirely; subprocesses inherit stdout from parent and don't need their own log file.

**This is the Python-idiomatic fix.** The whole reason `if __name__ == "__main__":` exists is exactly this scenario — module-level side-effects shouldn't fire on import.

**D2 — Verify subprocesses don't need terminal_output.md.**

`mp.get_context("spawn")` workers inherit stdout via inheritance — they print to the parent's terminal_output.md indirectly (parent's stdout is the file handle). Subprocess `print()` calls land in the parent's tee. No subprocess needs its OWN `_LOG_FILE`.

Verify by grep: any `import pipeline` followed by reads of `_LOG_FILE` or `_archived_log` from subprocess paths.

**D3 — Document the spawn-mode constraint inline.**

Above the `if __name__ == "__main__":` block, add a comment explaining the Windows-spawn-mode re-import behavior so future maintainers don't accidentally move module-level side-effects back out of the guard.

## §3.3 Anchor estimate (auditor Q5)

Mid-range: 5 anchors. Inclusive ±15% band: [4.25, 5.75].

Breakdown:
- D1: 2 anchors (archive call inside `__main__` guard + log-file-open inside `__main__` guard)
- D2: 2 anchors (subprocess test simulates spawn-mode re-import + verifies NO archive fired + NO PermissionError; verify pre-fix test catches the regression by removing the guard and confirming the test fails)
- D3: 1 anchor (inline comment present at the guard explaining Windows-spawn-mode constraint)

## §3.4 Pre-mortem (3 ways this fix could fail)

1. **D1 breaks something that depends on `_LOG_FILE` being available at module import** — e.g. a top-level `print(...)` somewhere in pipeline.py expecting tee to be wired. **Mitigation:** grep all `print(` calls at module-level in pipeline.py BEFORE the `if __name__ == "__main__":` block; any that need tee must move INSIDE the guard.
2. **D1 breaks tests that import pipeline** — pytest imports `pipeline` to test functions; if `_LOG_FILE` is only defined inside `__main__`, tests that need it will fail. **Mitigation:** existing tests should NOT depend on the side-effect of opening terminal_output.md; if they do, the test is wrong (it's using production stdout-tee in a test context); add a test fixture that mocks `_LOG_FILE` if needed.
3. **D2 verification test doesn't actually trigger spawn-mode re-import** — `pytest` doesn't auto-spawn subprocesses; the test needs to use `multiprocessing.spawn` explicitly. **Mitigation:** write the test using `multiprocessing.get_context("spawn").Process(target=lambda: __import__("pipeline"))` and assert no PermissionError surfaces.

## §3.5 Multi-direction invariant trace

- **Forward:** user runs `python pipeline.py` → `__name__ == "__main__"` → archive call fires (parent only) → child subprocesses re-import pipeline.py → `__name__ != "__main__"` in child → archive call skipped → no PermissionError → clean log.
- **Reverse:** if `__name__ == "__main__"` somehow fires inside a spawned child (shouldn't be possible on Windows-spawn), the archive call WOULD fire. Defensive: `print` the WARN at line 71-76 is fine; no functional regression even if guard fails.
- **Cross-spec:** P1.5 Session 81 (archive hook) — same author; this fixes the spawn-mode interaction Session 81 didn't anticipate. P0.R6 + R6.X/Y/Z (heavy-worker pools) — they introduced the spawn pattern; this fix accommodates without changing their architecture. P0.R13 D2 (size-cap rotation) — independent; size-cap path stays unchanged.

## §3.6 Cross-spec impact

- **Touches:** `pipeline.py` ONLY (D1 + D3 inline change; D2 is test-only).
- **Reads:** module-level imports unchanged.
- **Doesn't touch:** any other file.
- **Test surfaces:** `tests/test_p0_s12_terminal_output_archive_guard.py` NEW (~5 anchors); `tests/test_pipeline.py` may have a few imports-of-pipeline that need fixture adjustment if they rely on `_LOG_FILE`.

---

# Bundled-cycle interaction analysis

## §4.1 Independence verification

The three specs touch DIFFERENT surfaces:
- P0.S10: `core/brain.py` (prompt + tool description) + `pipeline.py::_intent_allows` (validator gate) + `core/config.py` (new regex constant)
- P0.S11: `tools/factory_reset.py` (NEW) + `core/db.py::wipe_all` (D2 summary)
- P0.S12: `pipeline.py` (module-level guard) ONLY

**Pipeline.py touched by S10 AND S12.** S10 edits `_intent_allows` (around line 815). S12 edits module-level structure (lines 81 + 83 + 200-204). NO LINE OVERLAP. Sequential merge order doesn't matter; either can land first.

## §4.2 Shipping order recommendation

**Architect's lean:** ship P0.S12 FIRST (it's the smallest + cleanest + lowest blast radius; 5 anchors; no LLM judgment dependency). Then P0.S11 (separate file mostly; 6 anchors). Then P0.S10 (LARGEST; 8 anchors + LLM-judgment dependency that needs canary re-validation).

Rationale: get the easy wins out first; build closure-audit momentum; then the LLM-judgment-sensitive spec gets the cleanest validation environment.

**Auditor Q4 — disagree?** Alternative orderings: (a) S10 first because it's the most user-visible blocker; (b) all three in parallel (no shared surface). Architect's lean is sequential S12→S11→S10 because canary Day 2 onward depends on clean terminal_output (S12) + clean factory reset (S11) — those should be in place before S10's LLM-judgment validation runs.

## §4.3 Cumulative scope

- **Anchors:** 8 (S10) + 6 (S11) + 5 (S12) = 19 anchors cumulative
- **D-decisions:** 3 + 3 + 3 = 9 cumulative
- **Cycles:** 3 OPTIONAL-Plan-v2 candidates (each SMALL-MEDIUM band; no architect-side scope expansion expected)
- **Architect time:** Phase 0 (this audit) + Plan v1 × 3 + closure × 3 = 7 artifacts. Per locked +1-per-artifact convention: spec-first review cycle bumps by ~7 across cumulative.
- **Developer time:** ~1-2 days for all 3 implementations sequential. ~6 hours if parallel.

## §4.4 Canary re-run trigger

After all 3 specs close: re-run canary Day 1 with the SAME scenarios that surfaced these bugs. Expected:
- P0.S10 validated: brain does NOT fire `report_identity_mismatch` on topic-correction; user can correct "no job" without dispute
- P0.S11 validated: `python tools/factory_reset.py --confirm` runs cleanly + summary log shows everything deleted + next boot shows FAISS rebuild from 0 rows
- P0.S12 validated: pipeline boot shows ONE archive log line + NO repeated PermissionError WARNs during run

**On canary re-pass:** continue with Day 1's other sessions OR pivot to P1.A1 per user's strategic call.
**On canary re-fail with new findings:** file additional sub-specs under same strict-mode discipline.

---

# Open questions for auditor

## Q1 — D3 in P0.S10: ship or defer?

D3 is the structural validator gate (regex-based identity-claim grounding). D1+D2 are prompt + tool-description tightening (LLM-judgment-dependent). Three options:

- **(a)** Ship all 3. Defense-in-depth; maximum safety net. Cost: +4 anchors + 1 new regex constant in config.
- **(b)** Ship D1 + D2 only; defer D3 unless canary re-run still shows misfires. Lighter cycle (~4 anchors). Risk: another canary cycle if LLM judgment fails again.
- **(c)** Ship D1 + D3 only; skip D2 tool-description. Tool description already has guidance the LLM ignored; adding more text may have diminishing returns. Cost: -1 anchor.

**Architect's lean: (a).** P0.S10 is a CRITICAL fix (canary surfaced active misclassification firing tool); defense-in-depth has the lowest blast radius for cost; Session 50+ + P0.S7.5.2 D5 set the precedent for multi-layer fixes on identity-confusion.

## Q2 — D1 in P0.S11: standalone CLI vs additive flag on existing entry point?

Option (a): NEW `tools/factory_reset.py` standalone script (per §2.3 D1).
Option (b): add a `--factory-reset` flag to `pipeline.py` itself (pipeline.py becomes both the run-target AND a reset-target with the flag).

**Architect's lean: (a) standalone tool.** Separation of concerns; existing tools/ pattern (replay_session.py etc.); easier to test in isolation; doesn't muddy `pipeline.py`'s 7000-line surface further.

## Q3 — Bundled vs sequential closure-audit cadence?

Option (a): close each spec individually (3 separate closure-audits + 3 separate coverage matrix updates).
Option (b): close as a bundle (one closure-audit covering all 3 specs, matching P0.B5 precedent).

**Architect's lean: (a) sequential.** Reasons: (i) the bundle is documentary only (Phase 0 convenience), not architectural; (ii) each spec's grep-verify surface is distinct; (iii) closure-audit verdict forwarding per §9 commitment is cleaner per-spec; (iv) P0.B5's bundle was 4 D-decisions IN ONE CYCLE; this is 3 separate cycles documented together.

## Q4 — Shipping order (sequential)?

**Architect's lean:** S12 → S11 → S10 (per §4.2). Alternative orderings welcomed.

## Q5 — Anchor estimates calibration?

S10: 8 anchors. S11: 6. S12: 5. Total: 19. Auditor mid-ranges for each individually solicit. If auditor's mids differ ±20%, flag for Q5 closure trajectory tracking.

## Q6 — Doctrine firings (procedural)?

Two doctrines fire on this Phase 0 audit:
- **`### Architect-reads-production-code-before-sign-off`** — grep-verified all 3 root causes against actual code (not pre-audit framing). Mark as 28th supporting instance.
- **`### Phase-0-granular-decomposition-enables-accurate-estimates`** — each D-decision has named edit site (`core/brain.py:809`, `pipeline.py:815`, etc.). Bump to 28th supporting instance pending closure-actual count.

Auditor confirm or correct firings.

## Q7 — Test count baseline?

Current cumulative suite (per CLAUDE.md): 2760 passed + 14 skipped + 9 xfailed.

Post-bundle expected: 2760 + 19 new anchors = 2779 passed. (Skipped + xfailed counts unchanged unless cross-cut regressions surface.)

---

# Summary

3 independent bugs surfaced in 1 canary session. All 3 grep-verified to specific code surfaces. Estimated 1-2 architect days cumulative + 6 anchors S11 + 5 anchors S12 + 8 anchors S10 = 19 cumulative anchors across 3 sequential cycles.

Architect requests auditor feedback on Q1-Q7 before proceeding to Plan v1 drafting.