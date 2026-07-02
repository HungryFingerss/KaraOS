# Follow-up #123 — Extend the P0.4 silent-except invariant to falsy-return swallows

**Status:** LOCKED — auditor GREENLIGHT 2026-05-31. Ready for the developer.
**Lineage:** post-canary follow-up #2 of 4 (order: #129 ✓ → **#123** → #128 → #126). This is the
PI-3 the auditor flagged in the first Canary #3 verdict — extend P0.4 from `except: pass` to the
`except: return <falsy>` class that hid the original embed bug.

**Auditor disposition (folded in below):** GREENLIGHT D1 + D2 + D2b + D3. Q1 = LOG the Kuzu read
(`:3872`) + the enrollment gate (`:676`), ANNOTATE `# OPTIONAL:` the health pings (`:543/:561`).
Q2 = D2b widen the window, with the short-handler scoping caveat documented IN-CODE. Q3 = include
D2, with the **detector run (not the Phase-0 count) as the authoritative enumeration**. Three PIs:
**PI-1 (sharpest) — consolidate the duplicated `_scan_file`/`_detect_in_source` detection into one
shared helper** (else the self-tests validate a different detector than production — Canary-#3-stub
vacuity cousin); PI-2 — guard-clause negative self-test; PI-3 — `_safe_loads` confirmed internal
(annotate). Closure gate in §7.

---

## 0. Phase 0 — grep + AST-measured findings (the count is a hint, NOT a contract)

**Current detector** (`tests/test_silent_except_invariant.py`): scans top-level `core/*.py`
(`glob`, NON-recursive) + 7 root files, allowlists `core/_minifasnet`, flags broad-except
(`bare`/`Exception`/`BaseException`) handlers whose body is EXACTLY `[ast.Pass]` with no permitted
annotation (`# RACE:`/`# CLEANUP:`/`# OPTIONAL:`) in a 3-line window.

**AST measurement:** 7 BARE-SILENT falsy-return violations in the CURRENT scan scope
(`brain.py:543`+`:561` return False; `brain_agent.py:296` None / `:2906` `[]` / `:3872` `{}`;
`heavy_worker.py:687` None; `pipeline.py:676` return False); recursive-`core/` widening adds **0**
new falsy-returns in nested dirs + surfaces the `producer.py:572` annotation-window gap (already
annotated, see D2b). 38 logged-then-return handlers (correctly NOT flagged) + 3 already-annotated.

**Q3 CONDITION (the authoritative-enumeration rule).** "7 falsy + 0 nested" are Phase-0 AST
measurements bounded by the falsy-shape-set + scope. The developer's ACTUAL D1+D2 detector run
(RED-first, listing every flagged site) is the authoritative enumeration — triage every flagged
site; do NOT hard-code "exactly 7" or "exactly the producer gap" anywhere in the tests or spec
follow-through. If the recursive run surfaces a real nested falsy-return the Phase-0 measurement
missed, it gets triaged too. The detector actually run, full suite green after triage, IS the
completeness proof.

**Bucket-C catch:** `heavy_worker.py:687` (`except Exception: return None` wrapping the pyannote
diarization SUBPROCESS inference call) is a genuine Canary-#3-class silent-None the pass-only
detector was blind to. Note the detector's correct scoping — the same function's `:676` (`return []`
empty-audio guard) + `:679` (`return None` pipeline-None guard) are GUARD CLAUSES, not except
bodies, and are correctly ignored (PI-2 pins this).

---

## 1. Decisions

### D1.0 — consolidate the detector into ONE shared decision helper (PI-1, foundational, do FIRST)
`_scan_file` (production scan) and `_detect_in_source` (synthetic self-tests) currently each
independently implement broad-except + body-shape + annotation-window. With the detector growing
(pass-only OR falsy-return, two body-shape paths, a wider annotation window), divergence is now
material: D1/D2b applied to one but not the other → the self-tests validate a DIFFERENT detector
than the one scanning production (the exact Canary-#3 conftest-stub vacuity class). Extract:

```python
def _handler_is_violation(node: ast.ExceptHandler, source: str) -> bool:
    """Single source of truth for the silent-except decision — BOTH _scan_file and
    _detect_in_source go through this, so a self-test can never validate a different
    detector than production scans (the B1 _build_and_insert / #129 C2 discipline)."""
    return (
        _is_broad_except_handler(node)
        and (_is_silent_pass_only_body(node.body)
             or _is_silent_falsy_return_body(node.body))
        and not _has_annotation_comment(source, node.lineno, node.end_lineno)
    )
```
Then a shared `_violations_in_source(source, label) -> list[str]` does the `ast.walk` +
`_handler_is_violation` + violation-string build; `_scan_file` (label=rel_str) and
`_detect_in_source` (label="<test>") both delegate to it. No walk/decide logic outside the shared
path. **An INV test asserts both entry points route through `_handler_is_violation`** (AST source
check) so a future edit can't re-fork them.

### D1 — falsy-return body-shape detector
`_is_silent_falsy_return_body(body)`: the body's LAST statement is a falsy `Return` (`return` bare,
`return None`, `return ""`, `return []`, `return {}`, `return ()`, `return 0`, `return False`, or
empty `set()/dict()/list()/tuple()` ctor) AND the handler body contains NO logging call
(`print`/`log`/`logger.{warning,error,info,debug,exception,critical,warn}`) AND no `raise`. Lives
behind `_handler_is_violation` (D1.0), so production + self-tests share it.

### D2 — widen the scan to recursive `core/`
`glob("*.py")` → `rglob("*.py")`, keeping the `core/_minifasnet` boundary-correct allowlist. Closes
the nested-`core/` blind spot (`core/vision/`, `core/event_log/`, `core/*_migrations.py`, …) for
BOTH pass-only AND falsy-return. Per Q3, the detector run is the authoritative enumeration — triage
whatever it flags.

### D2b — widen the annotation window to the full handler span (Q2)
`_has_annotation_comment` scans every line from `except_lineno-2` through `end_lineno` inclusive
(not just the 3-line set). Required by D2: otherwise it false-positives on `producer.py:572` (its
`# CLEANUP:` sits on line 573, between the `except:` carrying `# pragma: no cover` and the `pass`,
outside the current window). **In-code caveat (auditor Q2 scoping):** the full-span scan is safe
ONLY because every #123-detected shape is a SHORT handler (pass-only / single-falsy-return), so an
annotation anywhere in the handler is unambiguous. If a future body-shape ever adds LONG handlers,
the full-span scan could false-NEGATIVE (an unrelated annotation deep in a long handler clearing a
real violation) — note this assumption in the docstring so it isn't silently violated.

### D3 — triage the flagged sites (dispositions finalized; triage whatever the run flags)
| Site | Shape | Disposition (FINAL) |
|---|---|---|
| `heavy_worker.py:687` | pyannote subprocess → None | **LOG** `print(f"[Diarize] pyannote subprocess failed: {e!r}")` — the Canary-#3-class silent-None |
| `brain_agent.py:3872` | Kuzu RELATES_TO read → {} | **LOG** the graph-read failure (silent {} = degrades cross-person inference to "no graph knowledge" with no diagnostic — the `_kuzu_degraded`/P0.X class) |
| `pipeline.py:676` | enrollment-mishear DB error → False | **LOG** the fail-closed decision NAMING the intent ("voice_embedding_count failed → fail closed to dispute path"), KEEP `return False` (guards both the Jagan→Lexi corruption AND a persistently-broken gate silently never working) |
| `brain.py:543` / `:561` | health pings → False | **ANNOTATE** `# OPTIONAL:` NAMING the contract (ping failure = not-reachable; the CloudState SICK/OFFLINE transition + boot-health report surface the meaningful signal with their own logging — a per-ping log is redundant + noisy at 30s cadence) |
| `brain_agent.py:296` | optional `jellyfish` import | `# OPTIONAL:` (graceful degradation) |
| `brain_agent.py:2906` | `_safe_loads` JSON → [] | `# OPTIONAL:` (PI-3: confirmed internal — parses `room_summaries.topic_tags/safety_flags`, system-serialized JSON, NOT external/LLM input; the P0.12 adversarial-input concern does not apply) |

### D4 — self-tests + deliberate-regression (all route through the D1.0 shared helper)
Extend `test_detector_against_synthetic_sources` (which calls `_detect_in_source` → the shared
helper): `return None` / bare `return` / `return []` / `return {}` / `return False` / `return ""`
each CAUGHT; logged-then-`return None` NOT caught; annotated falsy-return NOT caught; narrow-except
falsy-return NOT caught. **PI-2 — guard-clause negative test:** a function with a falsy `return None`
in a GUARD CLAUSE (and/or function body) OUTSIDE any except, plus a separate flagged
`except: return None`, asserts ONLY the except is flagged (mirrors `heavy_worker.py`'s :676/:679
guards vs :687 except) — pins the except-scoping so a future refactor can't over-flag legitimate
guard returns. D2b gap-annotation test (the `producer.py:572` shape passes). D1.0 consolidation
test (both entry points route through `_handler_is_violation`).

---

## 2. Golden / closure
Structural-invariant micro-PR; the "golden test" IS the detector RED→GREEN: RED on the extended
synthetic CAUGHT cases + the injected production violation, GREEN after the triage. The single
behavioral change is the `heavy_worker:687` (+ `:3872` + `:676`) logs.

## 3. Behavioral-RED proof
(a) Inject `except Exception: return None` (unannotated, no log) at a fresh production line →
`test_no_unannotated_silent_excepts_in_production_code` FAILS naming the site → revert net-zero.
(b) **heavy_worker revert-reflag:** revert the `:687` log → the detector RE-flags it → restore —
proving the LOG (not an annotation) is what clears it.

## 4. Q rulings + PIs — RESOLVED (auditor 2026-05-31)
- **Q1 — RESOLVED:** LOG Kuzu `:3872` + enrollment `:676` (name the fail-closed intent); ANNOTATE
  `# OPTIONAL:` pings `:543/:561` (name the contract). All three architect leans confirmed (D3).
- **Q2 — RESOLVED:** D2b full-span window + the short-handler scoping caveat in the docstring.
- **Q3 — RESOLVED:** include D2; the detector RUN is the authoritative enumeration (§0 condition).
- **PI-1 — RESOLVED:** D1.0 shared `_handler_is_violation` helper + the route-through INV test.
- **PI-2 — RESOLVED:** D4 guard-clause negative self-test.
- **PI-3 — RESOLVED:** `_safe_loads` confirmed internal (`room_summaries` JSON) → `# OPTIONAL:` (D3).

## 5. Estimate
~9-10 logical anchors (auditor-confirmed): D1.0 shared helper + D1 falsy-shape + D2 rglob + D2b
window + the falsy self-test parametrize set (fan-out → ~1) + D2 nested-scan test + D2b gap test +
PI-2 guard-clause test + D1.0 route-through test + the heavy_worker/Kuzu/enrollment logs + the
grouped annotate triage + behavioral-RED. Actual count lands at closure.

## 6. Non-goals
- Does NOT touch `tests/` scan membership or the 7 root files' set (unchanged).
- Does NOT add `continue`/`break`-in-loop silent-swallow detection (separate body-shape; file #123.X
  if a canary surfaces it).
- The `:687` + `:3872` + `:676` logs are the only behavioral changes; everything else is the
  detector/test surface + annotations.

## 7. Closure gate (auditor-affirmed)
- Detector RED→GREEN on the extended synthetic corpus (D4 caught/allowed cases).
- §3 behavioral-RED (inject unannotated `except: return None` → invariant fires naming the site →
  revert) + the heavy_worker `:687` revert-reflag proof.
- **Full suite green** with the recursive-`core/` + falsy detector at 0 violations post-triage — that
  run is the authoritative enumeration per the Q3 condition (triage every flagged site, not "the 7").
- Layer-3 — architect independent full-suite run on the CUDA box + line-by-line, including: D1.0
  both entry points route through `_handler_is_violation`; the three logs land (not annotations) on
  `:687`/`:3872`/`:676`; the D2b caveat is documented; no hard-coded "7" anywhere.
