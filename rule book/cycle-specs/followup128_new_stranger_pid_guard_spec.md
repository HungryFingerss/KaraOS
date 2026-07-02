# Follow-up #128 — lock the reconciler `new_stranger` `claim.pid is None` guard (Canary #4 Q3)

**Status:** LOCKED — auditor GREENLIGHT 2026-05-31. Ready for the developer.
**Lineage:** post-canary follow-up #3 of 4 (order: #129 ✓ → #123 ✓ → **#128** → #126). The Canary #4
Q3 sibling: "audit the in-loop `new_stranger` path for an active KNOWN speaker." This is a
**clean-bill + structural lock**, not a bug fix — the audit found the invariant already holds; #128
turns it into a CI-enforced tripwire so it can't silently regress.

**Auditor disposition (folded in):** GREENLIGHT D1 + D2, no BLOCKING items. Clean-bill + gap both
independently grep-confirmed. Q1 = **co-locate** (D1 → `test_p10_routing_invariants.py`, D2 →
`test_p10_reconciler_contract.py` as the N-series pid-bearing sibling **N4b**). Q2 = **no
consumer-side tripwire** (the B1 sync-open is owned by Canary #4 / `SYNC_METHOD_ALLOWLIST`). Q3 =
**count-agnostic forall**, detector-run authoritative (current count independently verified as 3).
PI (refinement) = add a THIRD §2 scoping caveat documenting **D1-checks-present-not-gates, D2 is the
backstop**. Affirmed load-bearing: the #123 PI-1 shared-helper self-test discipline + the
non-`new_stranger` scoping self-test.

---

## 0. Phase 0 — the audit (grep + AST-verified against the current tree, post #123/#129; auditor-reconfirmed)

**The Q3 concern.** Canary #4 surfaced the pre-B1 race where a voice-first session-open was
async-invisible. Q3 asked the sibling question: in the in-loop router, can a `new_stranger` decision
fire for an **identified** (pid-bearing) speaker, mis-creating a phantom stranger session for someone
the voice channel already recognized? (The recurrent high-cost regression family that bit Canary #3
+ #4 — a known speaker's turn opening a stranger session, their words attributed to a phantom,
identity dropped.)

**Rule side — CLEAN.** `_resolve_actual_speaker` was DELETED at P0.10; the reconciler
(`core/reconciler.py`) is the sole router. Exactly 3 rules emit `action="new_stranger"`
(`:642`/`:671`/`:793`), and all three gate on `claim.pid is None` as the **first** condition
(`:635`/`:665`/`:782`): `_p4_pyannote_vouched_stranger`, `_p4_new_stranger_low_match`,
`_p5_no_session_new_stranger`. A pid-bearing claim can NEVER produce a `new_stranger` decision.

**Consumer side — CLEAN (B1).** The in-loop `elif _routing_action == "new_stranger":` branch
(`pipeline.py:8417`) opens via the **synchronous** `_open_session(...)` (`:8476`) — the Canary #4 B1
fix — so the stranger session is immediately visible.

**Existing coverage — the GAP (auditor-reconfirmed).** `test_p10_routing_invariants.py` locks
ordering / Bug-W / the `_routing_action` write-site / N7 — NOT the `new_stranger` guard.
`test_p10_reconciler_contract.py` tests the POSITIVE (`new_stranger` FIRES for pid=None:
C15/C19/C20b) and pid=None negatives — but every existing `action != "new_stranger"` negative is
built on `claim.pid=None`: **N2** (`:381`, gap-band sweep, `pid=None`), **N4** (`:431`,
multi-segment, `pid=None` despite its "cross-talk-between-knowns" docstring); **N3** (`:414`) is
pid-bearing but asserts *not misattribution*, NOT *not-new_stranger*. So the Q3 negative — a
pid-BEARING claim never routes to `new_stranger` — is genuinely uncovered, and the guard is
structurally unlocked.

**#128 = lock the gap.** D1 structural AST tripwire + D2 behavioral negative. Rule-side only.

---

## 1. Decisions

### D1 — structural AST tripwire (→ `tests/test_p10_routing_invariants.py`, co-located with the reconciler AST invariants)
A forward-property AST invariant over `core/reconciler.py`: for each rule `FunctionDef` whose body
emits `action="new_stranger"`, assert the body contains a `claim.pid is None` compare. **forall, not
"exactly 3"** (Q3) — the detector's run is the authoritative enumeration; a 4th `new_stranger` rule
landing later inherits the guard requirement automatically, and the forward test lists offenders
(currently 0).

**Shared-helper self-test discipline (#123 PI-1, load-bearing — affirmed).** Factor the decision into
ONE source-string helper `_new_stranger_rules_missing_guard(source) -> list[str]`; the forward test
(real `reconciler.py`) AND the self-tests route through it — no vacuity, no divergence (closes the
exact Canary-#3 conftest-stub / #123 duplicated-detector trap). Self-tests:
- (a) synthetic `new_stranger` emitter WITHOUT the guard → flagged;
- (b) WITH the guard → clean;
- (c) a NON-`new_stranger` rule (e.g. `action="current"`) without the guard → NOT flagged — the
  detector is scoped to `new_stranger` only. (Meaningful: grep shows 9 rules use `claim.pid is None`,
  only 3 emit `new_stranger`; the sibling `_p4_voice_ambiguous_*` / `_p5_no_session_no_action` gate
  on the same compare but emit other actions and MUST stay out of D1's scope.)

Detection shapes (auditor-confirmed sound): emits-new_stranger = an `ast.Constant("new_stranger")`
anywhere in the body (the `_CASCADE` `ast.Name` entries + the `:263`/`:571` docstring/comment refs
are NOT string-literal constants, so the scan hits exactly the 3 emission sites); the guard =
`ast.Compare(left=Attribute(Name("claim"),"pid"), ops=[Is], comparators=[Constant(None)])`.

### D2 — behavioral negative, framed as N-series contract **N4b** (→ `tests/test_p10_reconciler_contract.py`, beside N2/N4)
The runtime complement to D1 (defense-in-depth). Docstring names its lineage: the pid-BEARING sibling
of N2/N4 (which cover the pid=None axis). Two layers:
- **Per-rule (parametrized over the 3 rules):** construct inputs that WOULD fire the rule if pid were
  None (satisfy its other conditions), set `claim.pid = "lexi_002"` (an identified speaker), assert
  the rule returns `None` — isolates the guard's veto.
- **Reconcile-level sweep (N4b proper):** sweep a pid-bearing claim across conditions;
  `reconcile(...).action` is NEVER `"new_stranger"`. Mirrors the N2 sweep on the pid-bearing axis.

---

## 2. Scoping caveats (document in-code, per the #123 D2b precedent)
- **Literal-action scope:** D1 keys off the literal `"new_stranger"`. A future rule emitting the
  action via a variable (`action=some_var`) would not be detected — matches the current/expected
  style (literal action strings); note the assumption.
- **`is None` shape:** the guard detector targets the exact `claim.pid is None` compare. A guard
  written as `not claim.pid` or via a helper would be missed — the rules use `is None` uniformly;
  note the assumption.
- **D1 checks PRESENT, not GATES (PI — the D1/D2 division of labor).** D1 asserts the guard appears
  in the rule body, NOT that it structurally gates the `new_stranger` emission. A hypothetical future
  rule with `claim.pid is None` in some unrelated sub-expression that nonetheless emitted
  `new_stranger` unconditionally would PASS D1 but be a real bug — exactly what D2's behavioral
  negative backstops (a pid-bearing claim would reach the emission and fail the reconcile-level
  sweep). Document this in-code so a future reader does not assume D1 alone proves gating-correctness;
  D1 (structural, every-PR, fast-fail on "guard missing entirely") + D2 (behavioral, catches
  "present-but-ineffective") is the robust pair, and the reason both ship.

## 3. Open questions — RESOLVED (auditor 2026-05-31)
- **Q1 — RESOLVED: co-locate.** D1 → `test_p10_routing_invariants.py`; D2 → `test_p10_reconciler_contract.py`
  as **N4b** with explicit N2/N4 lineage in the docstring. (Discoverability: the rule-editor who could
  break the guard lives in these two canonical files; a dedicated file would fragment the suite.)
- **Q2 — RESOLVED: no consumer-side tripwire.** The `new_stranger` branch opens via the blessed sync
  `_open_session` (`:8476`), inheriting B1's synchronous-visibility guarantee that Canary #4
  (`SYNC_METHOD_ALLOWLIST` + that spec) already locks. The cross-cutting "all production session-opens
  route through sync `_open_session`, never a stray `create_task(open_session)`" single-open-path
  invariant is the #129-PI-2 item — it belongs to the session-lifecycle / Canary #4 domain; if it does
  not yet exist, file it there, NOT in #128. Phase-0 documents the consumer-side clean-bill.
- **Q3 — RESOLVED: count-agnostic forall.** Current flagged set independently verified as exactly 3;
  the spec's "3" is an accurate snapshot, but D1 asserts the forall, never a hard-coded count.

## 4. Estimate
~4-5 logical anchors: D1 forward AST tripwire + D1 self-tests (guardless-flagged / guarded-clean /
non-new_stranger-not-flagged) + D2 N4b per-rule behavioral negative (parametrize ×3 → ~1) + D2 N4b
reconcile-level sweep. Actual count lands at closure (detector run is authoritative).

## 5. Non-goals
- Does NOT modify `core/reconciler.py` or `pipeline.py` production code (clean-bill — nothing to fix).
- Does NOT re-lock the consumer-side B1 sync-open (Canary #4's domain; Q2 — and the single-open-path
  invariant is the #129-PI-2 item, filed there).
- Does NOT touch the cascade ordering / EXPECTED_RULES_BY_BAND invariants.

## 6. Closure gate (auditor-affirmed)
- D1 forward test green on the real `reconciler.py` (the 3 guarded rules pass; 0 offenders).
- D1 self-tests green (guardless synthetic → flagged; guarded → clean; non-new_stranger → not flagged).
- D2 N4b behavioral negatives green (pid-bearing claim → None per rule; reconcile never `new_stranger`).
- **Behavioral-RED:** inject a 4th synthetic `new_stranger`-emitting rule into `core/reconciler.py`
  WITHOUT the `claim.pid is None` guard → D1 forward test FAILS naming it → revert net-zero (the proof
  D1 catches the regression class, not a mock).
- Full suite green.
- Layer-3: architect independent full suite + line-by-line (the detector is non-vacuous per the
  shared-helper self-tests; D1 forall not hard-coded "3"; the three §2 scoping caveats documented
  in-code; D2 framed as N4b with N2/N4 lineage).
