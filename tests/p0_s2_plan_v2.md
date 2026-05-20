# P0.S2 — Dashboard Authentication — Plan v2

**Predecessor:** `tests/p0_s2_plan_v1.md`
**Status:** Plan v2 — auditor's 3 Plan v1 precision items addressed + 2 architect edge-case additions
**Mode:** Strict industry-standard + deferred-canary

Plan v2 is a refinement over Plan v1, not a rewrite. Sections below address only the deltas; everything else in Plan v1 stands.

---

## §1. Auditor Plan v1 precision items (3 — addressed)

### Q5-A — Enumeration clarity (banked-closures vs in-flight projections)

**Auditor's catch:** Plan v1 §10 called P0.S2 the "6th instance," conflating banked closures (post-actual) with in-flight projections (pre-closure). P0.S7.5.2 has banked (6 banked total: D-B, D-D, D-E, P0.S7.5, P0.S7.5.1, P0.S7.5.2). P0.S2 is the **7th data point** but the **1st in-flight projection** — its closure value is unknown until it actually closes.

**Plan v2 lock:** memory file `feedback_auditor_q5_estimates_trail_grep.md` updated 2026-05-20 with explicit Q5-A clarification:
- **Banked closures (6 instances, post-actual)**: D-B, D-D, D-E, P0.S7.5, P0.S7.5.1, P0.S7.5.2
- **In-flight projection (1, pending closure)**: P0.S2

The track record's predictive power lives in banked closures; in-flight projections reframe at closure. Operational Rule 5 added: enumeration scheme distinguishes the two timelines.

**P0.S2 self-framing correction:** Plan v1 §10 should have read "P0.S2 is the **1st in-flight projection** following 6 banked closures (4th consecutive ON-TARGET-with-slight-overage trajectory: 0% → 20% → 7% → 27% projected)." Locked in this Plan v2 §1.

### Q5-B — Upward-drift re-baseline rule

**Auditor's catch:** The drift trajectory 0% → 20% → 7% → 27% is NOT flat — it's upward. At 27%, the "slight overage" qualifier strains. The discipline name "Auditor-Q5-estimates-trail-grep" implies neutral bidirectional drift; 3 of last 4 instances HIGH (vs upper bound) is structural.

**Plan v2 lock:** memory file updated with `Re-baseline-trigger` rule:

- **IF next non-defense-in-depth cycle lands HIGH-BY-≥30% from auditor upper bound** → rename discipline to `Auditor-Q5-systematic-under-estimate`. Auditor re-baselines estimate-range methodology (wider bands accounting for precision-item additions).
- **ELSE if trajectory holds ≤27% across the next 2 cycles** → "slight overage" stands.
- **ELSE if trajectory reverses** → drift was transient; framing stable.

Precise trigger conditions banked:
- "Non-defense-in-depth cycle" = precision items from architect-side new edit sites / enumeration gaps, NOT auditor-driven defense-in-depth tests
- "HIGH-BY-≥30%" = `(actual - upper_bound) / upper_bound ≥ 0.30`
- "Next cycle" = spec after P0.S2 closes

This is the auditor-side analog of `feedback_auditor_precision_item_misframe.md`. Auditor remains honest about own estimation methodology — same discipline floor architect operates under.

### Q5-C — Test 27 patch target syntax

**Auditor's catch:** Plan v1 §2 D7 test 27 said "patch subprocess.run to spy." `_apply_windows_acl` does `import subprocess` at function scope (Plan v1 §1.P3 locked code, line 70). Function-scope imports cause `monkeypatch.setattr(subprocess, 'run', ...)` (after a top-level `import subprocess` in the test) to silently no-op — the patched attribute on the test-module's `subprocess` doesn't shadow the function's local re-import.

**Plan v2 lock:** Test 27 uses **string-form** `monkeypatch.setattr`:

```python
def test_windows_icacls_invocation(monkeypatch):
    import subprocess  # for CompletedProcess construction; not the patched site
    spy_calls = []
    def _spy(*args, **kwargs):
        spy_calls.append((args, kwargs))
        return subprocess.CompletedProcess(args=args[0], returncode=0,
                                            stdout='processed', stderr='')
    # String form — patches the *module attribute* so function-scope
    # `import subprocess; subprocess.run(...)` inside _apply_windows_acl
    # resolves to the patched attribute. The attribute form (after
    # `import subprocess` in this test) silently no-ops the spy because
    # _apply_windows_acl re-imports subprocess at call time.
    monkeypatch.setattr('subprocess.run', _spy)
    from core.dashboard_token import _apply_windows_acl
    _apply_windows_acl('/tmp/fake_token')
    assert len(spy_calls) == 1
    args, kwargs = spy_calls[0]
    cmd = args[0]
    assert cmd[0] == 'icacls'
    assert cmd[1] == '/tmp/fake_token'
    assert cmd[2:5] == ['/inheritance:r', '/grant:r']
    import getpass
    assert cmd[5] == f'{getpass.getuser()}:F'
    assert kwargs.get('check') is False
    assert kwargs.get('capture_output') is True
    assert kwargs.get('timeout') == 5.0
```

**Why string-form is correct here:** `monkeypatch.setattr('subprocess.run', spy)` replaces the attribute on the `subprocess` module itself (in `sys.modules`). Any code path that later does `import subprocess; subprocess.run(...)` — including function-scope imports — gets the patched value. The attribute-form `monkeypatch.setattr(subprocess, 'run', spy)` does the same thing IF the test's `subprocess` reference points to the same `sys.modules['subprocess']` object — which it does in normal Python. So the auditor's concern about silent no-op is actually more subtle than "function-scope imports break it." The risk is that a future refactor could change how `_apply_windows_acl` resolves `subprocess.run` (e.g., aliasing `from subprocess import run as _run`), at which point only string-form survives.

**Plan v2 disposition:** lock string-form per auditor's recommendation. It's strictly safer under future refactors AND functionally equivalent today.

Test 28 (`test_windows_icacls_failure_logs_warning_returns_false`) gets the same string-form patch shape.

---

## §2. Architect edge-case additions (2 — pre-mortem extension)

Auditor's §9 adjudication accepted these as legitimate Plan v2 candidates. Selected top 2 of 4: multi-tab race + token-file-corruption-recovery. Browser cookie eviction and partial cookie sent are lower-priority (browser eviction = user re-clicks new URL, same as token rotation; partial cookie = Set-Cookie header is atomic, cannot send partial). Both banked as known-limitations rather than pre-mortem entries.

### §3.12 — Multi-tab login race

**Failure:** User has the dashboard open in 2 tabs at first launch. Both tabs hit `/api/status` simultaneously and get 401. User clicks the auth URL in tab A — `.dashboard_auth_url` is consumed + cookie is set in tab A's browser context. Tab B still has its 401 page; it doesn't auto-refresh. User refreshes tab B; cookie is already set (same browser, same origin) → tab B works.

**This is the happy path.** The race condition is benign: cookies are scoped to origin, not to tab. Setting the cookie via tab A propagates to tab B implicitly.

**The actually-bad case:** user clicks the auth URL TWICE in quick succession (refresh of the URL, or click-spam). First click: token validates, cookie set, `.dashboard_auth_url` deleted, 302 redirect. Second click: `.dashboard_auth_url` may or may not exist by the second request's filesystem read. If it exists (race), no harm — token still validates against `.dashboard_token`. If it doesn't (delete completed), no harm — token still validates because `/api/auth` reads from `.dashboard_token` (the source-of-truth), not from `.dashboard_auth_url`.

**P4 invariant clarified:** `/api/auth` validates against `.dashboard_token` ONLY. The `.dashboard_auth_url` file's role is purely the user-facing convenience artifact. Validation never reads from `.dashboard_auth_url`. Delete-after-success is for the on-disk artifact's hygiene, NOT for the validation logic. Plan v2 locks this distinction in code review — the delete call is AFTER cookie is set, NOT before validation.

**Mitigation:** none needed. Race is benign by design. Banking as informational.

**Test (NEW, D2 → 6 tests):**
- `test_auth_double_click_succeeds_idempotently` — call `/api/auth?token=<correct>` twice in sequence; first call returns 302 + Set-Cookie + deletes `.dashboard_auth_url`. Second call: `.dashboard_token` still exists, validation still succeeds (Set-Cookie re-issued — harmless), URL file already gone (delete is best-effort ENOENT-tolerant). Both return 302. Behavioral.

### §3.13 — Token file corruption recovery

**Failure:** `.dashboard_token` is corrupted on disk — partially written due to disk-full mid-write, hardware fault, or filesystem corruption. Content is empty string OR contains binary garbage OR is truncated (e.g., 20 chars instead of 43). Middleware reads it, compares against cookie, length-mismatch fails timingSafeEqual → 401. User's cookie is the original correct token; mismatch is permanent until token is regenerated.

**Mitigation:** **Boot-check validates token shape.** Plan v2 locks `_verify_token_shape(content)` helper:

```python
import re
_VALID_TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{43}$')

def _verify_token_shape(content: str) -> bool:
    """Token shape from secrets.token_urlsafe(32) is exactly 43 urlsafe chars."""
    return bool(_VALID_TOKEN_RE.match(content))
```

`_ensure_dashboard_token()` at pipeline boot:
1. If file missing → generate.
2. If file exists, read content (UTF-8). Strip trailing whitespace (Unix tools may add newline).
3. If `_verify_token_shape(content)` is False → **log WARNING + back up corrupt file as `.dashboard_token.corrupt.<timestamp>` + regenerate**. Cookies tied to the corrupt token will 401; user must re-click new auth URL.

**Why back up rather than overwrite:** the corrupt file is forensic evidence — if filesystem corruption is widespread, the user / future-architect can inspect what happened. The `.corrupt` suffix excludes the file from any future regeneration check (only the canonical filename matters).

**Why regenerate rather than refuse to boot:** pipeline boot does not block on dashboard auth state. A corrupt token means a 1-time user re-onboarding; refusing to boot would prevent the user from finding the auth URL banner to recover. Self-heal is the right floor.

**Atomic-write reminder (D1 test 4):** `_atomic_write_secret()` writes to `.dashboard_token.tmp.<pid>` then `os.rename` to `.dashboard_token`. Crash mid-write leaves the tmp file (cleanup happens at next boot via `_cleanup_partial_writes()`); the canonical file is either present-and-valid or absent. Crash-window corruption of the canonical file is structurally impossible.

**Disk corruption (filesystem-layer) is still possible** (hardware fault, fsync skipped, journal lost). That's the case §3.13 mitigates via shape-validation + backup.

**Tests (NEW, D1 → 6 tests):**
- `test_corrupt_token_file_triggers_regenerate_and_backup` — write empty/garbage to `.dashboard_token`, call `_ensure_dashboard_token()`, assert: backup file exists with `.corrupt.<ts>` suffix containing original (garbage) content + new `.dashboard_token` exists with valid shape + WARNING log emitted.
- `test_valid_token_passes_shape_validation` — write valid 43-char urlsafe content, call `_ensure_dashboard_token()`, assert: no backup created, content unchanged.

---

## §3. Updated test surface — 28 → 30

| D | Plan v1 count | Plan v2 count | Delta |
|---|---|---|---|
| D1 (token generation) | 4 | **6** | +2 (corruption recovery) |
| D2 (auth route) | 5 | **6** | +1 (double-click idempotency) |
| D3 (middleware) | 5 | 5 | — |
| D4 (file read) | 2 | 2 | — |
| D5 (bind) | 5 | 5 | — |
| D6 (factory-reset) | 3 | 3 | — |
| D7 (mode/ACL) | 4 | 4 | — |
| **Total** | **28** | **30** | **+2** |

**Plan v2 lock: 30 tests.** Vs auditor's 16-22 estimate: **HIGH-BY-36%** at upper bound. **This crosses the Q5-B re-baseline trigger condition (≥30%)** — but P0.S2 is the **trigger-causing cycle**, not the "next cycle" that would activate the rename. Per the rule's "next non-defense-in-depth cycle" precision: the rename activates IF the NEXT spec after P0.S2 ALSO lands ≥30%. P0.S2 itself counts as the data point that motivates watching for the trigger.

**Subtle but important:** the +2 from Plan v2 ARE arguably defense-in-depth (corruption recovery + double-click idempotency are not motivating-failure regression guards — they're hardening for failure modes that haven't been observed). Per the rule's "non-defense-in-depth" exemption clause, +2 Plan v2 tests are exempt. **Plan v2 lock at 30 = Plan v1's 28 (architect-side new edit sites / enumeration gaps) + 2 (defense-in-depth).** Trigger calculation: 28 vs 22 upper bound = HIGH-BY-27% non-defense-in-depth. Still UNDER the 30% trigger, just barely.

**Banking precision:** Plan v2 §3 explicitly notes the +2 as defense-in-depth, exempt from trigger math. The trigger-relevant overage is 27% (Plan v1 lock), not 36% (Plan v2 total). Pattern stays in "slight overage" framing for P0.S2.

---

## §4. Pre-mortem updated count

Plan v1 had 11 failure modes (Phase 0 10 + §3.11 user-shares-faces). Plan v2 adds §3.12 multi-tab race + §3.13 token corruption recovery = **13 failure modes**.

Strict-mode discipline §1 minimum is 5-10; Plan v2 lands at 13. All have mitigation OR accepted-with-rationale tag.

---

## §5. 11-gate quality checklist (re-affirmed)

No gate changes from Plan v1. The +2 tests strengthen Gates 1 (Correctness — corruption recovery is a correctness property), 2 (Security — multi-tab race is a security/UX edge), 6 (Test pyramid), 7 (Regression guards — corruption recovery is a regression guard against silent partial-write).

All 11 gates remain APPLIES.

---

## §6. Deferred-canary `to_be_checked.md` entry (locked verbatim — Plan v2 final)

Plan v1 §8 entry is canonical-shape. Plan v2 adds 2 new PASS/FAIL signals reflecting the new tests:

**ADD to PASS signals:**
```
- Boot-check: corrupt .dashboard_token (manual edit to garbage) → next pipeline
  boot logs WARNING + creates .dashboard_token.corrupt.<ts> backup + regenerates
  valid token + writes new .dashboard_auth_url
- Double-click auth URL: both clicks return 302, cookie set, second click is
  idempotent no-op on .dashboard_auth_url (already deleted by first)
```

**ADD to FAIL signals:**
```
- Corrupt token file silently accepted (no backup, no regenerate)
- /api/auth crashes on second click of consumed URL (instead of idempotent 302)
```

**ADD to test scenario:**
```
14. Manually edit faces/.dashboard_token to garbage content → restart pipeline →
    expect WARNING + backup file + new token + dashboard auth URL re-issued
15. Click the auth URL twice in quick succession → expect 2× 302; cookie set
    once; auth-url file deleted on first click; second click harmless
```

Auditor cross-check at closure: entry lands verbatim in `c:\Users\jagan\dog-ai\to_be_checked.md`. Drift in wording = discipline failure flag.

---

## §7. Auditor-Q5 banking (Plan v2 final)

Per Q5-A enumeration scheme:
- P0.S2 is the **1st in-flight projection** following 6 banked closures
- Projection: HIGH-BY-27% at upper bound (28 tests vs 22) for non-defense-in-depth subset
- Plan v2 total HIGH-BY-36% (30 tests vs 22) — Plan v2 +2 are defense-in-depth, exempt
- Closure will re-baseline; track record updates with actual count

Per Q5-B trigger:
- P0.S2 sits at 27% (non-defense-in-depth), UNDER the 30% threshold
- The trigger activates on the NEXT spec after P0.S2 if IT lands ≥30%
- "Slight overage" framing holds for P0.S2; watch the cycle after

Memory file `feedback_auditor_q5_estimates_trail_grep.md` updated 2026-05-20:
- §Bidirectional-pattern section refactored to separate banked/in-flight
- New §Re-baseline-trigger section with precise condition
- Operational rule 5 added (enumeration scheme)
- §Trigger-threshold-for-elevation updated to reference P0.S2 as forthcoming 4th data point in the granular-Phase-0-correlation track

---

## §8. Strict-mode operational test (Plan v2)

- [x] Pre-mortem extended (§4 — 13 failure modes)
- [x] Multi-direction trace held from Plan v1 §6 (no new surfaces)
- [x] Quality-gate checklist re-affirmed (§5 — 11/11 APPLIES)
- [x] Cross-spec impact analysis re-verified (no changes; P0.S8 + P0.0.1 holds)
- [x] Closure-audit scheduled (executes per discipline at closure)

**Strict-mode 7th consecutive application.** (P0.S7.5.1 v1+v2+closure = 3; P0.S7.5.2 Phase 0+v1+v2+closure = 4; P0.S2 Phase 0+v1+v2 = 3 → total 10 applications across 3 distinct specs. Auditor's count "6th consecutive application" was at Plan v1 land; Plan v2 land is the 7th.)

Cross-spec generalization continues to hold.

---

## §9. Discipline counts (Plan v2 final)

- Spec-first review cycle: 17-for-17 at Plan v1; **18-for-18 at Plan v2 land** (per CLAUDE.md doctrine convention — each Plan v1/v2 cycle = +1 instance)
- Sub-pattern A (`Phase-0-catches-wrong-premise`): stays at 5 (no wrong-premise; P0.S2 ON-TARGET premise)
- Strict-industry-standard mode: **7th application banked**
- Deferred-canary strategy: 2nd application held (forecast entry locked verbatim ready for closure paste)
- Auditor-Q5: 6 banked closures + 1 in-flight projection (P0.S2)
- Phase 0 granularity sub-observation: 3 banked supporting instances (P0.S7.5 / P0.S7.5.1 / P0.S7.5.2) + 1 in-flight (P0.S2). Approaching elevation threshold (`### Phase-0-granular-decomposition-enables-accurate-estimates` candidate).

---

## §10. Plan v2 sign-off readiness

All 3 auditor precision items (Q5-A enumeration, Q5-B re-baseline, Q5-C patch syntax) addressed at code-precise + memory-precise level.

Both architect edge-case additions (§3.12 multi-tab, §3.13 corruption) banked with mitigation + tests.

Test count locked at 30 (with 27% non-defense-in-depth overage clearly named).

Pre-mortem at 13 failure modes (strict-mode minimum 5-10, exceeded).

Ready for joint architect+auditor sign-off → developer handoff.

---

## §11. Auditor Plan v2 sign-off — joint sign-off cleared 2026-05-20

Joint architect+auditor sign-off cleared. Plan v2 ACCEPTED with one non-blocking closure-narrative item.

### Non-blocking item to bank at closure

Auditor flagged a borderline in the defense-in-depth classification used for Q5-B trigger math:
- §3.13 token-corruption-recovery — solid defense-in-depth (unobserved failure mode + adversarial-input adjacent)
- §3.12 multi-tab double-click — borderline (real-world UX scenario AND hardening against unobserved second-click crash)

**Closure-narrative lock (recommended by auditor, accepted by architect):**

> **Operational definition of "defense-in-depth test":** verifies behavior under input that has NOT been observed in production AND would NOT be caught by the motivating-failure regression guard. Tests verifying real-world UX scenarios are behavioral-correctness, not defense-in-depth, regardless of how "edge-case" they feel.

Under this definition, on retrospective audit at closure:
- §3.13 corruption recovery → defense-in-depth (unobserved on user's machine; not caught by D3 motivating-failure guard)
- §3.12 multi-tab double-click → **reclassify as behavioral-correctness** (real-world UX; users do click links twice)

This means Plan v2's "+2 defense-in-depth" exemption math is actually "+1 defense-in-depth, +1 behavioral-correctness." Recalculated Q5-B trigger math:
- Plan v1 lock: 28 tests (architect-side enumeration gaps + auditor precision items) — HIGH-BY-27% from upper bound 22
- Plan v2 +1 behavioral-correctness (double-click idempotency) → 29 tests, HIGH-BY-32% non-defense-in-depth
- Plan v2 +1 defense-in-depth (corruption recovery) → exempt from trigger math

**Trigger math re-verification:** at HIGH-BY-32%, P0.S2 CROSSES the Q5-B 30% threshold. Per the rule, P0.S2 itself is the trigger-causing cycle; rename activates on the NEXT spec cycle if IT also lands ≥30%. P0.S2's own overage doesn't activate the rename — but it raises the watch.

**Auditor concurs (Plan v2 verdict):** P0.S2 sits AT THE 27%/32% boundary depending on classification. The boundary is what motivated banking the operational definition. Closure narrative locks the definition; future cycles use it as a hard rule.

**Lock the operational definition in `feedback_auditor_q5_estimates_trail_grep.md` at closure.** Plan v2 commits to do this in Phase 4 closure work (§10).

### Discipline counts at Plan v2 sign-off

- Spec-first review cycle: **18-for-18** ✓
- Sub-pattern A (Phase-0-catches-wrong-premise): stays at **5** ✓
- Strict-industry-standard mode: **7th consecutive application** ✓ (P0.S7.5.1 v1+v2+closure + P0.S7.5.2 Phase 0+v1+v2+closure + P0.S2 Phase 0+v1+v2 = 10 applications across 3 distinct specs; cross-spec generalization holds)
- Deferred-canary strategy: **2nd application held** (entry locked verbatim ready for closure paste)
- Auditor-Q5: 6 banked closures + 1 in-flight projection ✓
- Auditor-precision-item-misframe (auditor-side, parallel to architect-side): **2nd instance banked** (Q5-C function-scope import patch syntax) ✓
- Phase 0 granular-decomposition-enables-accurate-estimates (informal): 3 banked supporting instances + 1 in-flight ✓

---

## §12. Developer handoff

Joint sign-off cleared. Plan v2 is the implementation contract. Developer reads:
- `tests/p0_s2_audit.md` — Phase 0 audit (scope + D-decision rationale)
- `tests/p0_s2_plan_v1.md` — Plan v1 (locked implementation details)
- `tests/p0_s2_plan_v2.md` — Plan v2 (precision items + edge-case extensions; THIS file)

Per the spec-first review cycle convention, Plan v2 supersedes Plan v1 ONLY for the items it explicitly addresses (§1 + §2 + §3 + §11). Plan v1 §1-§9 stand unless contradicted in Plan v2.

### Implementation phases

**Phase 1 — Python side (~4-5h):**
- `core/dashboard_token.py` NEW
  - `_VALID_TOKEN_RE` regex constant (43-char urlsafe)
  - `_verify_token_shape(content) -> bool`
  - `_atomic_write_secret(path, content)` (write to `.tmp.<pid>` + rename)
  - `_restrict_to_owner(path)` (POSIX chmod + Windows icacls dispatch)
  - `_apply_windows_acl(path)` (subprocess+icacls with check=False + timeout=5.0 + WARNING-on-failure)
  - `_cleanup_partial_writes(faces_dir)` (rm any `.tmp.*` artifacts at boot)
  - `_write_auth_url(token, faces_dir)` (write `.dashboard_auth_url` mode 0600)
  - `_ensure_dashboard_token(faces_dir)` (the public entry point):
    1. Cleanup partial writes
    2. If `.dashboard_token` missing → generate + write atomic + restrict + write auth URL + log banner
    3. If `.dashboard_token` exists → read + shape-validate. If invalid: backup as `.dashboard_token.corrupt.<ts>` + regenerate + restrict + write new auth URL + WARNING log. If valid: verify mode is 0600 (POSIX) or run icacls (Windows); self-heal if drift.
- `pipeline.py::run()` call `_ensure_dashboard_token(FACES_DIR)` as the FIRST line in `run()` (before `_validate_env()` per pre-mortem §3.9)
- `core/db.py::wipe_all()` add comment naming preservation invariant
- Tests:
  - `tests/test_dashboard_token.py` — D1 (6), D4 (1 from Plan v1 D4 list — file-read invariant), D6 (1 — wipe_all preservation)
  - `tests/test_dashboard_token_windows.py` — D7 Windows (2, marked `@pytest.mark.skipif(sys.platform != 'win32')`)
  - Existing POSIX D7 (2) live in `test_dashboard_token.py` with `@pytest.mark.skipif(sys.platform == 'win32')`

**Phase 2 — Node.js side (~3-4h):**
- `dog-ai-dashboard/middleware.ts` NEW
  - Matcher: `['/api/:path*']`
  - Inline allowlist: `if (req.nextUrl.pathname === '/api/auth') return NextResponse.next()`
  - Read `.dashboard_token` (path resolved as `path.join(process.cwd(), '..', 'faces', '.dashboard_token')`)
  - On ENOENT → 401 `{error: "Pipeline not started — token not yet generated"}`
  - Compare cookie value vs file content via length-equality check then `crypto.timingSafeEqual(Buffer.from(...), Buffer.from(...))`
  - On mismatch → 401 `{error: "Unauthorized"}`
- `dog-ai-dashboard/app/api/auth/route.ts` NEW
  - GET handler, accepts `?token=X`
  - Reads `.dashboard_token`, length-check, `timingSafeEqual`
  - On success: Set-Cookie `dogai_session=<file-token>; HttpOnly; SameSite=Strict; Path=/; Max-Age=315360000` + delete `.dashboard_auth_url` (try/catch ENOENT-tolerant) + 302 redirect to `/`
  - On failure: 401, no Set-Cookie, no delete of auth URL
- `dog-ai-dashboard/app/api/factory-reset/route.ts:13-30` add comment naming preservation
- Tests:
  - `tests/test_dashboard_middleware.py` — D3 (5), D4 (1 — middleware returns 401 on missing token file)
  - `tests/test_dashboard_auth_route.py` — D2 (6 including double-click idempotency from §3.12), D6 (1 — auth-url preservation on failure)

Note: behavioral Node.js tests require either Next.js running OR Python-level subprocess-spawning. Locked at developer discretion — both approaches work. Recommended: `@pytest.mark.slow` + spawn Next.js dev server in pytest fixture, hit routes via `httpx`.

**Phase 3 — Launch wrapper (~2-3h):**
- `dog-ai-dashboard/scripts/launch.js` NEW
  - Reads `DASHBOARD_BIND` env var; default `127.0.0.1`
  - If `DASHBOARD_BIND === '0.0.0.0'` AND `DASHBOARD_BIND_ALLOW_ANY !== '1'` → process.exit(1) with hard error
  - If `DASHBOARD_BIND` non-default → stderr WARNING block (6 lines per Phase 0 §2.D5)
  - Validates `DASHBOARD_BIND` matches `^[a-zA-Z0-9.:_-]+$` (prevent argv injection)
  - Spawns `next dev|start --hostname <value> --port 3000` via `child_process.spawn` with stdio inherited
  - `--dry-run` flag for testing: prints the would-be command + exits 0
- `dog-ai-dashboard/package.json:5-9` change to `"dev": "node scripts/launch.js dev"`, `"start": "node scripts/launch.js start"`
- Tests:
  - `tests/test_dashboard_launch_script.py` — D5 (4)

**Phase 4 — Closure (~1-2h):**
- Refactor `tests/test_dashboard_bind_tripwire.py::test_dashboard_package_json_scripts_explicitly_bind_localhost` to detect launch.js wrapper pattern (per D5 + Plan v1 §1.P3)
- Run Windows ACL tests on user's machine (verify icacls invocation matches §1.P3 spec)
- Full suite green check
- Closure narrative: CLAUDE.md Session entry + complete-plan.md P0.S2 status flip + `to_be_checked.md` paste verbatim per §6 + memory file finalizations:
  - `feedback_auditor_q5_estimates_trail_grep.md` lock the **operational definition of defense-in-depth test** per §11 closure-narrative item
  - Bank Q5-B trigger result (27% non-defense-in-depth OR 32% with classification clarification; closure narrative names which)
- Auditor cross-check on `to_be_checked.md` entry — verbatim landing required

### Estimated total developer effort: 1.5-2 days

**On closure:**
- P0.S2 is the 2nd application of deferred-canary strategy
- Bundled with the existing post-P0.R11 canary-week scenario
- 3rd application of deferred-canary coming on the NEXT P0/P1 spec under the same discipline

**End of Plan v2.**
