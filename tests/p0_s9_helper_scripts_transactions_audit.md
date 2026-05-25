# P0.S9 Phase 0 audit — Helper scripts transactions + paired-write sibling correctness

**Status:** APPROVED 2026-05-22 by auditor with 4 precision items for Plan v1 absorption.

**Pre-audit framing (parent `complete-plan.md:647-650`):**

```
### P0.S9 — Helper scripts lack transactions
**Status:** `[OPEN]` `[VERIFY]`
**Fix:** wrap destructive operations in single SQLite transaction; `--dry-run` and `--confirm` flags.
```

**Phase 0 outcome:** Pre-audit framing PARTIALLY ACCURATE — grep surfaced a real correctness bug bigger than the original flag-discipline framing. Sub-pattern A 9th instance candidate (opposite-direction subspecies; pre-audit thought scope was X — flag discipline — partially valid but lower priority; grep revealed load-bearing item is Y — P0.5 sibling pattern violation in `core/audit.py` + inverse-check coverage gap).

---

## §1. Helper-script inventory + destructive-operation surface

Pass-1 grep enumeration of repo-root helper scripts + their destructive operations:

| Script | Destructive operation | Underlying primitive | P0.5/P0.9.1 status |
|---|---|---|---|
| `delete_person.py` | Person deletion (cross-DB) | `person_lifecycle.delete_person_everywhere()` → 4 sub-ops below | mixed (see sub-ops) |
| `person_lifecycle.py` | Step 1 — faces.db delete | `FaceDB.delete_person()` (core/db.py:804) | ✓ P0.5 wrapped |
| `person_lifecycle.py` | Step 2 — brain.db multi-table delete | `BrainDB.delete_person_data()` (core/brain_agent.py:3329) | ⚠ implicit transaction only |
| `person_lifecycle.py` | Step 3 — shadow_persons cleanup | `BrainDB.prune_shadows_mentioning()` (core/brain_agent.py:3379) | ⚠ implicit transaction only |
| `person_lifecycle.py` | Step 4 — Kuzu graph delete | `GraphDB.delete_person_entity()` | N/A (Kuzu) |
| `audit_person.py --repair` | Outlier embedding removal + FAISS rebuild | `core/audit.py::repair_gallery()` (audit.py:68-89) | **✗ P0.5 VIOLATION** |
| `repair_gallery.py --prune` | Outlier embedding removal + FAISS rebuild | `FaceDB.prune_outlier_embeddings()` (core/db.py:1858) | ✓ P0.5 wrapped |

**Note**: `audit_person.py --repair` and `repair_gallery.py --prune` do the SAME logical operation (delete outliers → rebuild FAISS) via TWO different code paths. One is P0.5-correct; the other is broken.

---

## §2. Grep-verified findings

### §2.1 Load-bearing finding — `core/audit.py::repair_gallery` violates P0.5 pattern

`core/audit.py:68-89`:

```python
def repair_gallery(person_id: str, db, mode: str = "flag") -> int:
    ...
    if mode == "remove" and outliers:
        ids = [o["row_id"] for o in outliers]
        placeholders = ",".join("?" * len(ids))
        db._conn.execute(f"DELETE FROM embeddings WHERE id IN ({placeholders})", ids)
        db._conn.commit()
        db._rebuild_faiss()
```

This violates the P0.5 canonical paired-write pattern on 4 axes:
1. NO `with db._index_lock:` outer (race against `recognize()` callers possible)
2. NO `with db.transaction():` inner for the DELETE (atomicity via single commit only)
3. NO `_mark_faiss_dirty()` sentinel before `_rebuild_faiss()` (boot reconciliation has no signal if rebuild crashes)
4. NO try/except around `_rebuild_faiss()` (any failure raises with no sentinel set; gallery diverges silently on next boot)

Sibling at `core/db.py:1858` (`FaceDB.prune_outlier_embeddings`) does the SAME logical operation with the full P0.5 pattern:

```python
with self._index_lock:
    with self.transaction():
        self._conn.execute(f"DELETE FROM embeddings WHERE id IN ({ph})", outlier_ids)
    try:
        self._rebuild_faiss()
    except Exception as e:
        print(f"[FaceDB] FAISS rebuild failed after prune_outlier_embeddings; will reconcile on next boot: {e!r}")
        self._mark_faiss_dirty()
        raise
```

**Bug fingerprint:** `audit_person.py --repair --id <pid>` routes through the broken path. Crash mid-DELETE or mid-rebuild leaves FAISS divergent from SQL embeddings table. No `_mark_faiss_dirty()` sentinel → `_load_faiss` on next boot doesn't trigger `_rebuild_faiss` reconciliation → silent gallery corruption.

### §2.2 P0.5 inverse-check coverage gap

`tests/test_faiss_atomicity_invariants.py::test_all_paired_write_sites_are_in_tuple` (the P0.5 inverse-check) only scans `core/db.py`. `core/audit.py` is outside scan surface. The P0.5 invariant has a coverage gap — the test passes (all destructive ops in core/db.py ARE in tuple) but a destructive op in core/audit.py escaped the scan entirely.

This is `### Induction-surfaces-invariant-gaps` doctrine territory — invariant has a coverage gap; this Phase 0 audit IS the gap-surfacing event. D3 closes the gap in same cycle per locked discipline (no defer).

### §2.3 Secondary finding — BrainDB implicit-transaction discipline drift

`BrainDB.delete_person_data` (core/brain_agent.py:3329-3377) and `BrainDB.prune_shadows_mentioning` (core/brain_agent.py:3379-3406) use IMPLICIT transactions:

```python
def delete_person_data(self, person_ids: list) -> int:
    ...
    for table in ("knowledge", "presence_log", "episodes", "prompt_prefs"):
        cur = self._conn.execute(...)
        total += cur.rowcount
    ...  # 4+ more DELETE statements
    self._conn.commit()  # single commit at end
    return total
```

Atomicity holds via Python's auto-BEGIN + `isolation_level="IMMEDIATE"` (P0.9.1 Imp-1) — all 7+ statements run in one implicit transaction, committed once. If any statement raises mid-loop, the next connection open implicitly rolls back the partial state.

But this is discipline-shape drift from P0.9.1's explicit `with self.transaction():` ratchet. Future maintainer adding an inner `.commit()` mid-loop would break atomicity silently. Same atomicity, weaker discipline.

### §2.4 Secondary finding — `delete_person.py` has no safety flags

`delete_person.py` argparse signature:

```python
parser.add_argument("--id", required=True, help="Person ID to delete")
```

That's it. `python delete_person.py --id jagan_001` triggers immediate cross-DB deletion. NO `--dry-run`, NO `--confirm`. Highest blast-radius script in repo.

`repair_gallery.py` has interactive `input("Continue? [y/N]")` (line 70) — works for interactive use, not scriptable. `audit_person.py --repair` treats the `--repair` flag itself as explicit confirmation (user typed it).

---

## §3. Out-of-scope (deferred to P0.S9.X or P0.X.Y)

1. **Cross-DB atomicity (faces.db → brain.db → Kuzu)** in `delete_person_everywhere`. Same class as P0.X but at 3-store granularity. SQLite transactions can't span databases; would need new sentinel + recovery design. Out of P0.S9 scope.
2. **`audit_person.py` + `repair_gallery.py` --dry-run/--confirm flags.** Both have implicit mechanisms (audit/repair modes; interactive prompt). Lower priority. Banked as P0.S9.X if operator pain point emerges.
3. **Other 28+ `self._conn.commit()` sites in BrainDB.** Plan v1 LOCK: D2 scope is EXCLUSIVELY `delete_person_data` + `prune_shadows_mentioning` (the 2 in destructive-person-lifecycle path). Other commit sites stay; future cycles migrate as needed.

---

## §4. D-decisions (4 D-decisions, decomposed with named edit sites)

### D1 (LOAD-BEARING — correctness fix)
**Disposition:** Consolidate by redirect.
**Files:** `audit_person.py:79` + `core/audit.py:68-89` + `core/audit.py:5` (docstring) + `tests/test_pipeline.py:8972` + `tests/test_pipeline.py:8993` + `KARAOS_KNOWLEDGE.md:1696`
**Edits:**
1. `audit_person.py:79` — replace `repair_gallery(person_id, db, mode="remove")` with `db.prune_outlier_embeddings(person_id)`.
2. `core/audit.py:68-89` — DELETE `repair_gallery` function entirely.
3. `core/audit.py:5` — UPDATE module docstring to remove `repair_gallery` reference.
4. `tests/test_pipeline.py:8972` (`test_repair_gallery_removes_outliers`) — DELETE (covered by existing `FaceDB.prune_outlier_embeddings` tests).
5. `tests/test_pipeline.py:8993` (`test_repair_gallery_flag_mode_does_not_modify`) — REWRITE against `FaceDB.gallery_audit` (equivalent semantic to mode='flag').
6. `KARAOS_KNOWLEDGE.md:1696` — UPDATE doc reference.

### D2 (DISCIPLINE-SHAPE)
**Disposition:** Explicit transaction wrapping for 2 BrainDB methods.
**Files:** `core/brain_agent.py:3329-3406` (delete_person_data + prune_shadows_mentioning)
**Edits:** Wrap each method's multi-step write block in `with self.transaction():`. Remove trailing `self._conn.commit()`. Scope cap: ONLY these 2 methods; 28+ other commit sites in BrainDB stay (per PI #2 below).

### D3 (INVARIANT-EXTENSION — closes coverage gap that surfaced this audit)
**Disposition:** Extend P0.5 inverse-check scan surface.
**Files:** `tests/test_faiss_atomicity_invariants.py:243` (`test_all_paired_write_sites_are_in_tuple`)
**Edits:** Change scan surface from `core/db.py` to glob `core/*.py` (top-level, NOT recursive) with `_SCAN_EXCLUDE` allowlist for any vendored subdirectories (per PI #4 below).

### D4 (FLAGS — polish)
**Disposition:** `delete_person.py` gains `--dry-run` and `--confirm` flags. Scope cap: delete_person.py ONLY (per PI #3 below).
**Files:** `delete_person.py` + new `_compute_delete_preview()` helper in `person_lifecycle.py`
**Edits:**
1. Add `--dry-run` flag (default False) — prints per-table row counts that WOULD delete; no destructive op.
2. Add `--confirm` flag (default False) — required for non-dry-run mode; default-deny gate exits 1 with error.
3. --dry-run takes precedence over --confirm (preview is safe, no destructive op).
4. New `_compute_delete_preview(person_id, faces_db, brain_orch)` helper in person_lifecycle.py — does SELECT counts across the 7+ tables `delete_person_data` would delete from. Read-only.

---

## §5. Cross-spec impact analysis

- **P0.5 (FAISS+SQL atomicity)** — D1 fix directly closes a P0.5-pattern violation that the P0.5 inverse-check missed. D3 extends the inverse-check to prevent recurrence. Same family-shape as P0.5.
- **P0.9.1 (explicit transaction discipline)** — D2 brings 2 BrainDB methods into compliance with the P0.9.1 ratchet (explicit `with self.transaction():` over implicit single-commit).
- **P0.X (brain.db ↔ Kuzu cross-write)** — out-of-scope for P0.S9; cross-DB atomicity in `delete_person_everywhere` is a separate concern banked as P0.X.Y.
- **P0.S2 (dashboard auth)** — orthogonal; helper scripts are CLI tools, not dashboard endpoints.

---

## §6. Pre-mortem (10 failure modes)

1. D1 consolidation breaks an unanticipated caller of `core/audit.py::repair_gallery` — PI #1 enumerates 4 surfaces; Pass-2 grep verified at Plan v1.
2. D2 explicit transaction wrap deadlocks if a caller already holds an outer transaction — `BrainDB.transaction()` docstring already covers nested-detection via `self._conn.in_transaction`; verified.
3. D3 extended scan surface false-positives on a legitimate destructive op that doesn't need P0.5 wrapping — `PAIRED_WRITE_METHODS` tuple is the allowlist; any false-positive resolves by registering the method.
4. D4 --confirm gate breaks existing CI scripts that call `delete_person.py` without --confirm — one-time migration cost; default-ON is the load-bearing safety contract per architect lean Q2.
5. D4 --dry-run preview undercounts vs actual delete (SELECT counts diverge from DELETE counts under race conditions) — acceptable; preview is approximate; production runs use explicit --confirm + see actual summary post-deletion.
6. D1 test rewrite (test_pipeline.py:8993) covers different semantic than original — Plan v1 §1.1 verifies `FaceDB.gallery_audit` returns `outlier_row_ids` without deletion (equivalent semantic to mode='flag').
7. D2 explicit-transaction wrap changes behavior for an outer caller already in a transaction — BrainDB internal use; verified no outer-callers of `delete_person_data` or `prune_shadows_mentioning` outside person_lifecycle.delete_person_everywhere.
8. D3 scan surface excludes a critical file (e.g., new vendored `core/event_log/`) — `_SCAN_EXCLUDE` allowlist surface is small + explicit; documented per Plan v1 §1.4.
9. D4 dry-run preview helper `_compute_delete_preview` has its own SELECT bugs (counting wrong tables, missing JSON-encoded source_speakers etc.) — preview helper directly mirrors `delete_person_data` SQL shape; same SQL bugs would affect both.
10. D1 deletion of `core/audit.py::repair_gallery` accidentally breaks `audit_person.py --repair` JSON output (which was previously reading `repair_gallery` return value) — Plan v1 §2.1 verifies the `db.prune_outlier_embeddings(person_id)` return value matches the existing JSON output contract.

---

## §7. Multi-direction invariant trace

### D1 forward invariant
After D1: `core/audit.py` contains NO `def repair_gallery`. All destructive-op call paths for outlier removal go through `FaceDB.prune_outlier_embeddings` (P0.5-correct).

### D1 inverse invariant
After D1: NO production caller invokes `core/audit.py::repair_gallery`. Pass-2 grep `repair_gallery` across repo finds zero remaining production references.

### D2 forward invariant
After D2: `delete_person_data` + `prune_shadows_mentioning` bodies contain `with self.transaction():` AND do NOT contain `self._conn.commit()` (trailing commit removed).

### D2 inverse invariant
After D2: NO write statement in either method's body sits OUTSIDE the `with self.transaction():` block.

### D3 forward invariant
After D3: P0.5 inverse-check scans `core/*.py` (top-level). Any future destructive op in any new `core/*.py` module gets caught.

### D3 inverse invariant
After D3: simulating a NEW destructive op in `core/audit.py` (or any other `core/*.py` outside `_SCAN_EXCLUDE`) without P0.5 wrapping → inverse-check fires.

### D4 forward invariant
After D4: `delete_person.py` has `--dry-run` flag + `--confirm` flag + default-deny gate (exits 1 when neither is present).

### D4 inverse invariant
After D4: `python delete_person.py --id X` (no flags) exits with non-zero status + error message naming required flag.

---

## §8. Open questions (4) — all adjudicated to architect leans at auditor verdict

- **Q1 — D1 disposition:** consolidate-by-redirect vs patch-in-place. **Architect lean: consolidate by redirect.** Auditor adjudication: **ACCEPTED** per `### Spec-contracts-not-implementations` discipline + duplicate-shape elimination.
- **Q2 — D4 --confirm default:** default-ON (require --confirm) vs default-OFF (require --no-confirm to skip). **Architect lean: default-ON.** Auditor adjudication: **ACCEPTED strongly** — cross-DB destructive op at highest blast radius; default-deny is load-bearing safety contract.
- **Q3 — D4 --dry-run output:** per-table summary vs "would delete person X". **Architect lean: per-table summary.** Auditor adjudication: **ACCEPTED** — matches `core/audit.py::gallery_audit` existing output shape + deferred-canary observable-preview philosophy.
- **Q4 — --dry-run × --confirm interaction:** dry-run skips --confirm vs dry-run still requires --confirm. **Architect lean: dry-run skips --confirm.** Auditor adjudication: **ACCEPTED** — logical (preview-only, zero side effects); UX (hostile to operators running dry-run first).

---

## §9. Q5 baseline estimation

NARROW band [5.95, 8.05] mid 7 (auditor adjudication accepted).

Caveat: PI #1 may shift upper bound by 1-2 anchors. If D1 counts replacement tests within D1's anchor count → band stays mid 7 (architect lean). If counted as separate anchors → band shifts to mid 8 within NARROW [6.8, 9.2].

Plan v1 LOCK: 7 anchors at exact mid (D1 replacement tests counted within D1's consolidation scope; reasoning per `### Spec-contracts-not-implementations`).

---

## §10. Sub-pattern A 9th instance candidacy

P0.S9 Phase 0 audit qualifies as 9th instance of `### Phase-0-catches-wrong-premise` doctrine (opposite-direction subspecies):

- Pre-audit framing: "Helper scripts lack transactions" — partially valid (D2 + D4) but misnames the load-bearing item.
- Grep evidence: load-bearing item is P0.5 sibling-pattern violation in `core/audit.py::repair_gallery` + the P0.5 inverse-check coverage gap. Both unrelated to the original transaction/flag framing.
- Same shape as P0.B6's stale-TODO-after-work-complete (8th instance, opposite-direction subspecies — pre-audit thought work was pending, grep revealed work was done elsewhere with different gap).

Banked at closure-time pending Plan v1 lock + closure-actual count alignment per honest-count commitment discipline.

---

## §11. Twin-filename pitfall check (11th preventive event candidate)

Pass-2 grep at audit drafting:
- `tests/p0_s9_*.md` — zero pre-existing files. ✓ Clean disambiguation.

11th preventive event of `### Twin-filename-pitfall-prevention`. Doctrine instance count holds at 7 per locked enumeration rule (preventive events tracked separately; only gap-catches bump the count).

---

## §12. Verdict + handoff

**Auditor verdict:** Phase 0 ACCEPTED 2026-05-22 with 4 precision items for Plan v1 absorption:
- **PI #1 (HIGH):** D1 scope expansion — Pass-2 grep enumerate 4 affected surfaces (banked as `Plan-v1-Pass-2-grep-undercount` 4th instance candidate).
- **PI #2 (MEDIUM):** D2 scope cap — explicit 2-method-only scope.
- **PI #3 (MEDIUM):** D4 scope cap — `delete_person.py` ONLY.
- **PI #4 (LOW):** D3 scan surface — option (b) top-level `core/*.py` glob + `_SCAN_EXCLUDE` allowlist.

**Q5 LOCK:** NARROW band [5.95, 8.05] mid 7.

**Architect leans Q1-Q4:** all ACCEPTED.

**Next:** Plan v1 absorbs all 4 PIs proactively; auditor's Plan v1 verdict ratifies the locked plan.
