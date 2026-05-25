# P0.S9 Plan v1 — Helper scripts transactions (D1+D2+D3+D4 contract lock + 4 PI absorption)

**Phase 0 base:** `tests/p0_s9_helper_scripts_transactions_audit.md` (auditor APPROVED 2026-05-22 with all 4 architect leans accepted on Q1-Q4 + Q5 band locked NARROW [5.95, 8.05] mid 7 + 4 precision items absorbed at Plan v1).

**Phase 0 outcomes:** Sub-pattern A 9th instance candidate banked pending closure (opposite-direction subspecies; pre-audit framing was flag-discipline-focused, grep revealed P0.5 sibling-pattern violation in `core/audit.py::repair_gallery`). 6th OPTIONAL-Plan-v2 path candidate (under absorbed sub-rule per P0.S8 closure) if Plan v1 clears 0 items.

**Plan v1 absorbs (proactively, all 4 precision items from auditor verdict):**

- **P1** §1.1 — Pass-2 grep enumeration of `repair_gallery` references (4 surfaces enumerated explicitly + 5th decoupled-by-execFile surface banked honestly).
- **P2** §1.2 — D2 scope cap (ONLY `delete_person_data` + `prune_shadows_mentioning`; 28+ other commit sites stay).
- **P3** §1.3 — D4 scope cap (`delete_person.py` ONLY; `audit_person.py` + `repair_gallery.py` already have implicit mechanisms).
- **P4** §1.4 — D3 scan surface lock (option (b) top-level `core/*.py` glob + `_SCAN_EXCLUDE` allowlist for vendored subdirs).

Cadence prediction: **v1 only OPTIONAL-Plan-v2 path candidate (6th absorbed sub-rule proof case if Plan v1 absorbs cleanly)**. Escalates to v2 if auditor surfaces ≥1 unresolved item.

---

## §1. P1-P4 — precision item absorption

### §1.1 PI #1 (HIGH) — D1 scope: 4 enumerated `repair_gallery` references + 5th decoupled surface

Pass-2 grep over `.py` + `.md` surfaces confirmed:

| # | Surface | Reference type | Disposition |
|---|---|---|---|
| 1 | `audit_person.py:17` | `from core.audit import audit_gallery, repair_gallery` | EDIT: drop `repair_gallery` from import |
| 2 | `audit_person.py:79` | `removed = repair_gallery(person_id, db, mode="remove")` | EDIT: replace with `removed = db.prune_outlier_embeddings(person_id)` |
| 3 | `core/audit.py:5` | Module docstring naming `repair_gallery` | EDIT: remove `repair_gallery` line from docstring |
| 4 | `core/audit.py:68-89` | Function definition | DELETE entire function |
| 5 | `tests/test_pipeline.py:8972-8990` | `test_repair_gallery_removes_outliers` (function deletion test) | DELETE entire test (P0.5 coverage exists via `tests/test_faiss_atomicity_invariants.py` + `tests/test_faiss_sql_atomicity.py`) |
| 6 | `tests/test_pipeline.py:8993-9008` | `test_repair_gallery_flag_mode_does_not_modify` (mode='flag' test) | REWRITE against `FaceDB.gallery_audit` (equivalent semantic — returns `outlier_row_ids` without deletion) |
| 7 | `KARAOS_KNOWLEDGE.md:1696-1701` | Function doc entry | DELETE section; add 1-line pointer to `FaceDB.prune_outlier_embeddings` reference in the audit_gallery section above |

**5th surface — honestly banked (not in D1 scope; decoupled by execFile pattern):**

`dog-ai-dashboard/app/api/gallery-audit/[id]/route.ts` (DELETE handler at line 41-73) invokes `audit_person.py --repair --json` via `execFile()` — the route does NOT directly import or call `repair_gallery`. After D1's redirect at `audit_person.py:79`, the route still works correctly because `audit_person.py` internally now calls `db.prune_outlier_embeddings()` (P0.5-correct path). Banking honestly: D1 makes the dashboard route SAFER (P0.5 atomicity restored to the route's destructive op) without requiring any TypeScript edit.

**6th + 7th surfaces — out of scope (no edit required):**

- `core/brain_agent.py:6448` — message text references `repair_gallery.py` (the SCRIPT, not the function). SCRIPT stays.
- `pipeline.py:3753` — comment references `repair_gallery.py` (SCRIPT). Stays.
- `tools/bulk_annotate_p04.py:37` + `tests/test_silent_except_invariant.py:34` — allowlist entries for `repair_gallery.py` SCRIPT name. Stay.

**Disambiguation lock:** P0.S9 D1 deletes the `core/audit.py::repair_gallery` FUNCTION ONLY. The `repair_gallery.py` SCRIPT stays — it invokes `FaceDB.prune_outlier_embeddings` directly (P0.5-correct path; not affected by D1).

**Banking — `Plan-v1-Pass-2-grep-undercount` 4th instance:** architect's Phase 0 conversational findings to Jagan didn't enumerate these 4 affected surfaces explicitly; auditor's Pass-2 grep at verdict surfaced them. Plan v1 §1.1 absorbs the corrective enumeration. Same family as P0.B3 D1 test_kuzu_crash_injection.py undercount + P0.B5 D3 test monkeypatch undercount + P0.B6 D1 test self-reference undercount. Memory file (`feedback_plan_v1_pass2_grep_undercount.md`) bumps 3 → 4 instances. Watch criteria: 5+ instances may elevate to operational rule extension under `feedback_spec_time_grep_verification.md`.

### §1.2 PI #2 (MEDIUM) — D2 scope cap to 2 BrainDB methods

Pass-2 grep confirmed 30+ `self._conn.commit()` sites across `core/brain_agent.py` (BrainDB class):

```
lines 1201/1215/1263/1357/1377/1413/1462/1478/1506/1525/1544/1602/
      1638/1671/1679/1696/1734/1986/1996/2061/2084/2126/2144/2154/
      2163/2174/2184/... (auditor verdict)
```

**D2 scope LOCK (EXCLUSIVELY):**
- `core/brain_agent.py:3329-3377` — `delete_person_data` (multi-table delete in `person_lifecycle.delete_person_everywhere` path)
- `core/brain_agent.py:3379-3406` — `prune_shadows_mentioning` (multi-row UPDATE + DELETE in same destructive path)

**Out of D2 scope:** the other 28+ `commit()` sites in BrainDB. They stay. Future cycles may migrate as needed (banked candidate for P0.S9.X if discipline drift surfaces). Per architect's `### Discipline-count-bump-needs-explicit-justification` sub-rule — broadening D2 beyond the 2 destructive-person-lifecycle methods would be scope creep without explicit justification.

### §1.3 PI #3 (MEDIUM) — D4 scope cap to `delete_person.py`

**D4 scope LOCK:** `delete_person.py` ONLY.

**Out of D4 scope:**
- `audit_person.py` — `--repair` flag itself acts as explicit user confirmation (typing the flag is the confirmation gate); D1 redirect routes the destructive op through the P0.5-correct path with boot reconciliation as the safety net. No additional flag discipline needed.
- `repair_gallery.py` — has interactive `input("Continue? [y/N]")` at line 70 (works for interactive use; not scriptable, but operator pain point hasn't emerged).

**Banked as P0.S9.X follow-up:** if operator pain point emerges with `audit_person.py` or `repair_gallery.py` needing scriptable `--dry-run` / `--confirm`, file separately.

### §1.4 PI #4 (LOW) — D3 scan surface lock at option (b)

**D3 scan surface LOCK:** option (b) top-level `core/*.py` glob + `_SCAN_EXCLUDE` allowlist for vendored subdirectories.

```python
# tests/test_faiss_atomicity_invariants.py — D3 scan surface
_SCAN_EXCLUDE = frozenset({
    "core/_minifasnet",     # vendored MiniFASNet model code (no destructive SQL ops)
    "core/event_log",       # vendored event-log path (P0.0.7 producer surface; out-of-scope per allowlist)
})

def _scan_paths():
    """Return list of core/*.py top-level files (not recursive); skip vendored subdirs."""
    core_dir = Path("core")
    return [
        p for p in core_dir.glob("*.py")  # top-level only
        if not any(str(p).startswith(exc) for exc in _SCAN_EXCLUDE)
    ]
```

**Rejected options:**
- Option (a) explicit 2-file list `[core/db.py, core/audit.py]` — brittle to future sibling additions; recreates the coverage gap that triggered this audit.
- Option (c) recursive glob `core/**/*.py` — pulls in vendored code already covered by P0.4 allowlist; over-broad.

Option (b) is the future-proof choice — new sibling additions like `core/db_helpers.py` would auto-enter scan surface without per-file registration.

---

## §2. D-decisions — full contract lock

### §2.1 D1 LOCK — Consolidate by redirect (delete broken duplicate; eliminate drift surface)

**Edits (in order):**

```python
# audit_person.py:17 — BEFORE
from core.audit import audit_gallery, repair_gallery

# audit_person.py:17 — AFTER
from core.audit import audit_gallery
```

```python
# audit_person.py:78-79 — BEFORE
r = audit_gallery(person_id, db)
removed = repair_gallery(person_id, db, mode="remove")

# audit_person.py:78-79 — AFTER
r = audit_gallery(person_id, db)
removed = db.prune_outlier_embeddings(person_id)
```

```python
# core/audit.py:5 — BEFORE (module docstring)
repair_gallery(person_id, db, mode)  — 'flag' (list) or 'remove' (delete + rebuild)

# core/audit.py:5 — AFTER (module docstring)
[line removed; only audit_gallery remains in docstring inventory]
```

```python
# core/audit.py:68-89 — DELETE entire function body
def repair_gallery(person_id: str, db, mode: str = "flag") -> int:
    ...  # 22-line function deleted
```

```python
# tests/test_pipeline.py:8972-8990 — DELETE test entirely
def test_repair_gallery_removes_outliers(tmp_path):
    ...

# tests/test_pipeline.py:8993-9008 — REWRITE
def test_repair_gallery_flag_mode_does_not_modify(tmp_path):
    """repair_gallery(mode='flag') only counts outliers without deleting."""
```

The REWRITTEN test becomes:

```python
def test_gallery_audit_returns_outlier_ids_without_modification(tmp_path):
    """FaceDB.gallery_audit() returns outlier_row_ids without modifying the DB.
    P0.S9 D1 replacement: was test_repair_gallery_flag_mode_does_not_modify;
    mode='flag' was a no-op preview equivalent to direct gallery_audit() call.
    """
    db = _build_db_with_outliers(tmp_path)  # same fixture as deleted test
    pre_count = db._conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    results = db.gallery_audit(person_id="dave")
    assert results, "gallery_audit should return non-empty results"
    assert "outlier_row_ids" in results[0]
    post_count = db._conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    assert post_count == pre_count, "gallery_audit must not modify DB"
```

**KARAOS_KNOWLEDGE.md:1696-1701 edit:**
- DELETE the entire `### repair_gallery(person_id, db, mode) → int` section.
- ADD a 1-line note to the `audit_gallery` section above (line 1670s) pointing to `FaceDB.prune_outlier_embeddings` for the destructive operation.

**Discipline anchors (D1):**
- **D1 Anchor 1** (source-inspection): `core/audit.py` contains NO `def repair_gallery`.
- **D1 Anchor 2** (source-inspection): `audit_person.py` contains `db.prune_outlier_embeddings(person_id)` AND does NOT contain `repair_gallery(`.

### §2.2 D2 LOCK — Explicit `with self.transaction():` wrapping for 2 BrainDB methods

**Edits:**

```python
# core/brain_agent.py:3329-3377 — BEFORE
def delete_person_data(self, person_ids: list) -> int:
    if not person_ids:
        return 0
    ph = ",".join("?" * len(person_ids))
    total = 0
    for table in ("knowledge", "presence_log", "episodes", "prompt_prefs"):
        cur = self._conn.execute(...)
        total += cur.rowcount
    # ... 4+ more DELETE statements
    self._conn.commit()  # <-- single implicit-transaction commit
    return total

# core/brain_agent.py:3329-3377 — AFTER
def delete_person_data(self, person_ids: list) -> int:
    if not person_ids:
        return 0
    ph = ",".join("?" * len(person_ids))
    total = 0
    with self.transaction():  # <-- explicit BEGIN IMMEDIATE / COMMIT
        for table in ("knowledge", "presence_log", "episodes", "prompt_prefs"):
            cur = self._conn.execute(...)
            total += cur.rowcount
        # ... 4+ more DELETE statements (all inside transaction)
    # NO trailing self._conn.commit() — transaction context manager owns commit
    return total
```

Same pattern for `prune_shadows_mentioning` (core/brain_agent.py:3379-3406).

**Discipline anchors (D2):**
- **D2 Anchor 1** (source-inspection): `delete_person_data` body contains `with self.transaction():` AND does NOT contain `self._conn.commit()` (trailing commit removed).
- **D2 Anchor 2** (source-inspection): `prune_shadows_mentioning` body contains `with self.transaction():` AND does NOT contain `self._conn.commit()`.

### §2.3 D3 LOCK — Extend P0.5 inverse-check scan surface to `core/*.py` (top-level)

**Edits at `tests/test_faiss_atomicity_invariants.py:232-260`:**

Current code (Plan v1 §1.4 PI #4 reference shape):

```python
def test_all_paired_write_sites_are_in_tuple():
    """Inverse check: every method in core/db.py with FAISS write markers IS in PAIRED_WRITE_METHODS."""
    src = Path(DB_PATH).read_text(...)  # DB_PATH = "core/db.py"
    tree = ast.parse(src)
    # ... scan for paired-write patterns
```

Migrate to scan multiple paths:

```python
_SCAN_EXCLUDE = frozenset({"core/_minifasnet", "core/event_log"})

def _scan_paths() -> list[Path]:
    """Return list of core/*.py top-level files (not recursive); skip vendored subdirs."""
    core_dir = Path("core")
    paths = []
    for p in core_dir.glob("*.py"):
        if not any(str(p).startswith(exc) for exc in _SCAN_EXCLUDE):
            paths.append(p)
    return paths

def test_all_paired_write_sites_are_in_tuple():
    """Inverse check: every method across core/*.py (top-level) with FAISS write markers IS in PAIRED_WRITE_METHODS."""
    for path in _scan_paths():
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        # ... scan for paired-write patterns
```

**Discipline anchors (D3):**
- **D3 Anchor 1** (source-inspection): test file contains `_scan_paths` (or equivalent helper) AND `_SCAN_EXCLUDE` constant AND the scan iterates `core/*.py` (top-level glob, NOT recursive `**/*.py`).

### §2.4 D4 LOCK — `delete_person.py` `--dry-run` + `--confirm` flags + default-deny gate

**Edits at `delete_person.py`:**

```python
# delete_person.py — AFTER (full rewrite below; ~50 LOC)
"""
delete_person.py — Delete a person from every store.

Usage:
    python delete_person.py --id "jagan_abc123" --dry-run     # preview only
    python delete_person.py --id "jagan_abc123" --confirm     # actual destructive run

REQUIRES --dry-run OR --confirm. Default-deny on destructive cross-DB op
per P0.S9 D4 safety contract (highest blast radius script in repo).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.db import FaceDB
from core.brain_agent import BrainOrchestrator
from core.config import BRAIN_DB_PATH, GRAPH_DB_PATH, FACES_DIR
from person_lifecycle import delete_person_everywhere, compute_delete_preview

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete a person from every store (cross-DB destructive op)")
    parser.add_argument("--id", required=True, help="Person ID to delete")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview deletions without committing (safe; no destructive op)")
    parser.add_argument("--confirm", action="store_true",
                        help="Required for non-dry-run mode (default-deny on destructive op)")
    args = parser.parse_args()

    # P0.S9 D4 default-deny gate — destructive op requires explicit flag.
    if not args.dry_run and not args.confirm:
        print("[Delete] ERROR: destructive op requires --confirm or --dry-run",
              file=sys.stderr)
        print("        Use --dry-run first to preview; --confirm to execute.", file=sys.stderr)
        sys.exit(1)

    person_id = args.id
    faces_db = FaceDB()
    row = faces_db.get_person(person_id)
    if not row:
        print(f"[Delete] Person not found: {person_id}")
        faces_db._conn.close()
        sys.exit(1)

    person_name = row["name"]
    brain_orch = BrainOrchestrator(BRAIN_DB_PATH, GRAPH_DB_PATH)

    if args.dry_run:
        # P0.S9 D4 dry-run path — preview only; NO destructive call.
        preview = compute_delete_preview(person_id, person_name, faces_db, brain_orch)
        print(f"[Delete --dry-run] {person_name} ({person_id}) — would remove:")
        for k, v in preview.items():
            print(f"  {k}: {v}")
        faces_db._conn.close()
        brain_orch.close_connections()
        sys.exit(0)

    # Actual destructive path (--confirm gate passed).
    summary = delete_person_everywhere(person_id, person_name, faces_db, brain_orch)
    faces_db._conn.close()
    brain_orch.close_connections()

    photo = FACES_DIR / f"{person_id}.jpg"
    if photo.exists():
        photo.unlink()
        summary["photo"] = "removed"

    print(f"[Delete] {person_name} ({person_id}) — fully removed")
    for k, v in summary.items():
        print(f"  {k}: {v}")
```

**New helper in `person_lifecycle.py`:**

```python
def compute_delete_preview(
    person_id: str,
    person_name: str,
    faces_db: FaceDB,
    brain_orch: BrainOrchestrator,
) -> dict:
    """P0.S9 D4 dry-run preview — count rows that would be deleted across all stores.

    Read-only; no commits. Mirrors delete_person_everywhere SQL shape but does
    SELECT COUNT instead of DELETE. Per-table counts surfaced to operator before
    destructive op runs.
    """
    preview: dict = {}

    # faces.db tables
    fc = faces_db._conn
    preview["faces.embeddings"] = fc.execute(
        "SELECT COUNT(*) FROM embeddings WHERE person_id = ?", (person_id,)
    ).fetchone()[0]
    preview["faces.voice_embeddings"] = fc.execute(
        "SELECT COUNT(*) FROM voice_embeddings WHERE person_id = ?", (person_id,)
    ).fetchone()[0]
    preview["faces.conversation_log"] = fc.execute(
        "SELECT COUNT(*) FROM conversation_log WHERE person_id = ?", (person_id,)
    ).fetchone()[0]
    preview["faces.persons"] = 1 if faces_db.get_person(person_id) else 0

    # brain.db tables
    bc = brain_orch.brain_db._conn
    for table in ("knowledge", "presence_log", "episodes", "prompt_prefs"):
        preview[f"brain.{table}"] = bc.execute(
            f"SELECT COUNT(*) FROM {table} WHERE person_id = ?", (person_id,)
        ).fetchone()[0]
    preview["brain.proactive_nudges"] = bc.execute(
        "SELECT COUNT(*) FROM proactive_nudges WHERE target_person_id = ?", (person_id,)
    ).fetchone()[0]
    preview["brain.social_mentions"] = bc.execute(
        "SELECT COUNT(*) FROM social_mentions WHERE source_person_id = ?", (person_id,)
    ).fetchone()[0]
    preview["brain.inter_person_relationships"] = bc.execute(
        "SELECT COUNT(*) FROM inter_person_relationships WHERE person_a = ? OR source_speaker = ?",
        (person_id, person_id),
    ).fetchone()[0]

    # Kuzu graph (name-collision aware; mirrors delete_person_everywhere logic)
    name_shared = fc.execute(
        "SELECT COUNT(*) FROM persons WHERE name = ? AND id != ?",
        (person_name, person_id),
    ).fetchone()[0]
    preview["graph.Entity"] = (
        f"would delete (name='{person_name}', unique)" if not name_shared
        else f"SKIP (name shared by {name_shared} other(s))"
    )

    return preview
```

**Discipline anchors (D4):**
- **D4 Anchor 1** (source-inspection): `delete_person.py` argparse has `--dry-run` flag AND `--confirm` flag.
- **D4 Anchor 2** (source-inspection): `delete_person.py` has default-deny gate — `if not args.dry_run and not args.confirm: ... sys.exit(1)` pattern present.

### §2.5 Deliberate-regression checks (induction-surfaces-invariant-gaps protocol)

Phase 5 must execute:
- **(a)** Re-add deleted `core/audit.py::repair_gallery` function (paste back the deleted 22-line body) → D1 Anchor 1 fails (`def repair_gallery` found in `core/audit.py`).
- **(b)** Drop `with self.transaction():` from `delete_person_data` (revert to implicit `self._conn.commit()` at end) → D2 Anchor 1 fails (no `with self.transaction():` substring).
- **(c)** Add a NEW destructive op in `core/audit.py` without P0.5 wrapping (e.g., temporary `def _test_destructive_delete(db, pid): db._conn.execute('DELETE FROM persons WHERE id = ?', (pid,))`) → D3 Anchor 1 fires via P0.5 inverse-check (after D3 extension, the new method gets caught).
- **(d)** Remove `--dry-run` flag from `delete_person.py` argparse → D4 Anchor 1 fails.
- **(e)** Drop default-deny gate from `delete_person.py` (remove the `if not args.dry_run and not args.confirm: sys.exit(1)` block) → D4 Anchor 2 fails.

All 5 reverts must fire correctly + revert cleanly.

---

## §3. Test surface — 7 anchors (Plan v1 LOCK at exact mid)

| D-decision | Anchor count | Anchor types |
|---|---|---|
| D1 (consolidate by redirect) | 2 | source-inspection: no `def repair_gallery` in core/audit.py + audit_person.py calls `db.prune_outlier_embeddings` |
| D2 (explicit transaction wrap) | 2 | source-inspection per method: `delete_person_data` + `prune_shadows_mentioning` each contain `with self.transaction():` and no trailing `_conn.commit()` |
| D3 (inverse-check coverage extension) | 1 | source-inspection: `_scan_paths` helper + `_SCAN_EXCLUDE` + top-level glob (NOT recursive) |
| D4 (dry-run + confirm + default-deny gate) | 2 | source-inspection: --dry-run + --confirm flags + default-deny gate logic |
| **TOTAL** | **7** | (D1 test rewrites count within D1's scope per architect lean Q5 caveat; not separate anchors) |

**Q5 LOCK: 7 anchors at exact mid 5 ± 15% NARROW band [5.95, 8.05] = 0% ON-TARGET.** 5th consecutive 0% exact-mid Q5 forecast at Plan v1 lock (P0.B5 + P0.B6 + P0.S8 Plan v1 + P0.S8 closure + P0.S9 Plan v1).

---

## §4. Closure-actual projection per `Explicit-closure-honest-count-commitment` (13th instance MADE here)

**Architect commits BEFORE closure** per `Explicit-closure-honest-count-commitment` discipline (13th instance candidate, to be HONORED at closure-audit as 14th instance per STRICT separation):

NARROW band [5.95, 8.05] mid 7 closure projections:

| Closure-actual | Math vs mid 7 | Disposition | Doctrine effect |
|---|---|---|---|
| ≤5 anchors | `≤−28.6%` | **FALSIFICATION TRIGGER** | **DEMOTES 12 → 11 supporting** |
| 6 anchors | `−14.3%` | SLIGHT-DRIFT-DOWN (within ±15% band) | HOLDS at 12 |
| **7 anchors (Plan v1 LOCK)** | `0%` | **ON-TARGET** (exact mid) | **BUMPS 12 → 13 supporting** |
| 8 anchors | `+14.3%` | SLIGHT-DRIFT-UP (within ±15% band) | HOLDS at 12 |
| ≥9 anchors | `≥+28.6%` | **FALSIFICATION TRIGGER** | **DEMOTES 12 → 11** |

NARROW band; only exact 7 bumps doctrine. 6 or 8 = SLIGHT-DRIFT (HOLDS); ≤5 or ≥9 = FALSIFICATION.

Honest acknowledgment: if Phase 5 surfaces an 8th anchor (e.g., D4 Anchor 3 splits into separate --dry-run vs --confirm tests), closure-actual lands SLIGHT-DRIFT-UP. Or if D1 anchors 1+2 collapse into a single source-inspection test, closure-actual lands SLIGHT-DRIFT-DOWN. Honest reading applied regardless.

---

## §5. P4 — Closure-narrative paste-template (5-surface landing per P0.B3/P0.B5/P0.B6/P0.S8 precedent)

### §5.1 CLAUDE.md line ~3

When P0.S9 closes, prepend above P0.S8 entry:

```
| **P0.S9 (Helper scripts transactions + paired-write sibling correctness) CLOSED 2026-05-XX** — Closes the P0.5 sibling-pattern violation in `core/audit.py::repair_gallery` that the P0.5 inverse-check missed + 2 BrainDB explicit-transaction migrations + inverse-check coverage extension + `delete_person.py` safety flags. 4 D-decisions in a SMALL-band cycle. **D1 (CORRECTNESS — load-bearing)**: `audit_person.py:79` redirected from `repair_gallery(...)` to `db.prune_outlier_embeddings(...)`; `core/audit.py::repair_gallery` function DELETED entirely; 2 obsolete tests + 1 doc reference cleaned up. Consolidation-over-patch per `### Spec-contracts-not-implementations` discipline. **D2 (DISCIPLINE-SHAPE)**: `BrainDB.delete_person_data` + `prune_shadows_mentioning` migrated from implicit single-commit to explicit `with self.transaction():` wrapping. Atomicity equivalent; matches P0.9.1 ratchet. **D3 (INVARIANT-EXTENSION)**: P0.5 inverse-check `test_all_paired_write_sites_are_in_tuple` extended from `core/db.py`-only to `core/*.py` (top-level glob + `_SCAN_EXCLUDE` for vendored subdirs). Closes the coverage gap that originally hid the D1 violation. **D4 (SAFETY FLAGS)**: `delete_person.py` gains `--dry-run` (preview per-table row counts) + `--confirm` (default-deny gate); `compute_delete_preview()` helper added to `person_lifecycle.py`. **Total P0.S9 LOGICAL ANCHORS: 7** (Plan v1 §3 LOCK EXACT MATCH). **Q5 closure under MID-RANGE methodology**: auditor mid 7, Plan v1 lock 7, **closure actual 7** (exact mid; NARROW band [5.95, 8.05] only 7 anchors qualifies ON-TARGET). **Overage: 0% — ON-TARGET**. Doctrine `### Phase-0-granular-decomposition-enables-accurate-estimates` **BUMPS 12 → 13 SUPPORTING INSTANCES**. Plan v1 §4 honest-count commitment HONORED — **14th instance of `Explicit-closure-honest-count-commitment` discipline** (13th MADE at Plan v1 §4, 14th HONORED at closure per STRICT separation). **5/5 deliberate-regression confirmations PASSED**. **Sub-pattern A 9th instance** banked — opposite-direction subspecies (pre-audit framing was flag-discipline-focused; grep revealed load-bearing P0.5 violation in `core/audit.py`). `### Phase-0-catches-wrong-premise` **8 → 9 instances**. **`### Induction-surfaces-invariant-gaps` 8 → 9 instances** — the P0.5 inverse-check coverage gap (only scanned `core/db.py`, missed `core/audit.py`) IS the inducted-invariant-gap; D3 closes it in same cycle. **`Plan-v1-Pass-2-grep-undercount` 3 → 4 instances** (Phase 0 conversational findings undercounted 4 affected surfaces; Plan v1 §1.1 absorbed corrective enumeration). **6th OPTIONAL-Plan-v2 proof case** under the absorbed sub-rule (P0.S3 + P0.B3 + P0.B5 + P0.B6 + P0.S8 + P0.S9). **`### Zero-precision-items-at-auditor-review` doctrine 7 → 9 instances** (Phase 0 8th + Plan v1 9th). **Strict-industry-standard mode 48 → 51 applications + 14 → 15 closures**. Twin-filename pitfall 10 → 11 preventive events (no pre-existing P0.S9 artifacts at audit drafting). **Cumulative suite**: 2607 → ~2607 (D1 deletes 2 obsolete tests + adds 7 new anchors; net delta -2+7 = +5; equivalent count to Plan v1 LOCK 7 logical anchors mod the 2 deleted tests).
```

### §5.2-§5.4 parent + subdir `complete-plan.md` + `to_be_checked.md`

Per P0.B3/P0.B5/P0.B6/P0.S8 precedents. Twin-filename pitfall discipline at status flip (parent + subdir).

### §5.5 Memory files

- `feedback_explicit_closure_honest_count_commitment.md`: bump 12 → 14 instances (Plan v1 §4 MADE 13th + closure HONORED 14th per STRICT).
- `feedback_phase_0_zero_precision_items_at_auditor_review.md`: bump 7 → 9 instances (Phase 0 8th + Plan v1 9th if both clear at 0 items each at auditor review surfaces).
- `feedback_plan_v1_pass2_grep_undercount.md`: bump 3 → 4 instances.
- `feedback_doctrine_prediction_precision_improving_over_arc.md`: extend 4-cycle 0% streak to 5-cycle 0% streak (P0.S9 Plan v1 lock at exact mid + closure exact mid).

---

## §6. Cross-spec impact analysis

See Phase 0 §5 — verified clean. P0.5 (FAISS+SQL atomicity), P0.9.1 (explicit transaction discipline), P0.X (brain.db ↔ Kuzu cross-write), P0.S2 (dashboard auth) all explicitly enumerated. P0.S9 strengthens P0.5 + P0.9.1 disciplines; orthogonal to others.

---

## §7. Quality gate checklist (10 APPLIES + 1 N/A privacy)

Per strict-mode 11-gate floor:

1. ✅ Phase 0 audit completed + auditor-approved with 4 precision items absorbed (`### Zero-precision-items-at-auditor-review` does NOT fire at Phase 0; P0.S9 absorbs the 4 PIs at Plan v1 instead — opportunity to fire at Plan v1 review).
2. ✅ Plan v1 absorbs all 4 precision items proactively (PI #1 enumerated 4 surfaces + 5th decoupled-by-execFile honestly banked; PI #2-#4 scope caps locked).
3. ✅ D-decisions have unambiguous contracts — D1 at §2.1 + D2 at §2.2 + D3 at §2.3 + D4 at §2.4.
4. ✅ Pre-mortem coverage — 10 failure modes documented at Phase 0 §6.
5. ✅ Multi-direction invariant trace per D-decision — Phase 0 §7.
6. ✅ Cross-spec impact analysis — Phase 0 §5.
7. ✅ Spec-time grep-verification (Pass-1 + Pass-2) — Phase 0 §1-§2 (Pass-1) + Plan v1 §1.1-§1.4 (Pass-2). Spec-time grep-verification 25 → 26 instances.
8. ✅ Honest-closure-actual-count commitment made at Plan v1 §4 — 13th instance to be banked.
9. ✅ Deliberate-regression check protocol — §2.5 enumerates 5 induced reverts.
10. ✅ Closure-narrative paste-template ready — §5 5-surface template + §3 band-table.
11. N/A Privacy — helper scripts operate on persons' own identifiers (no cross-person leak; pid-scoped destructive ops).

---

## §8. Discipline counts at Plan v1 close

| Discipline | Phase 0 close | Plan v1 close |
|---|---|---|
| Spec-first review cycle | 58 | **59** ✓ |
| Strict-industry-standard mode | 48 + 14 closures | **49 applications + 14 closures** ✓ |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 12 supporting | stays 12 (closure pending; ON-TARGET candidate at 7 anchors → bump 12 → 13) |
| `### Phase-0-catches-wrong-premise` | 8 | stays 8 (closure pending; sub-pattern A 9th instance candidate → bump 8 → 9 at closure) |
| `### Twin-filename-pitfall-prevention` | 7 + 4 op rules | stays 7 (11th preventive event; doctrine count holds per locked enumeration rule) |
| `### Grep-baseline-before-drafting` | 15 | **16** ✓ |
| `### Zero-precision-items-at-auditor-review` | 7 | stays 7 (Phase 0 returned 4 PIs — NOT zero; Plan v1 audit pending; if 0 items → 8th instance) |
| Deferred-canary | 16th in-flight | stays 16 (closure event pending) |
| Auditor-Q5-estimates-trail-grep | 18 banked | stays 18 + 1 in-flight |
| Cross-cycle-handoff transparency precedent | 21 | **22** ✓ |
| Architect-reads-production-code-before-sign-off | 11 banked | stays 11 (closure-audit pending) |
| Sub-pattern A (in `### Phase-0-catches-wrong-premise`) | 8 | stays 8 (9th candidate pending closure) |
| Spec-time grep-verification | 25 instances | **26** ✓ |
| Discipline-count-bump-needs-explicit-justification | 11 preventive | stays 11 |
| Convention-drift-on-discipline-counts | 5 | stays 5 |
| Per-artifact-arithmetic-drift-survives-grep-baseline | 1 | stays 1 |
| `Explicit-closure-honest-count-commitment` | 12 | **13** ✓ (Plan v1 §4 commitment MADE) |
| `Auditor-catches-Q5-math-at-plan-review` | 2 | stays 2 |
| `Plan-v1-Pass-2-grep-undercount` | 3 | **4** ✓ (Phase 0 conversational findings undercounted 4 surfaces; Plan v1 §1.1 corrective enumeration) |
| `Bug-fix-cycles-surface-discipline-edges` | 1 | stays 1 |
| `Auditor-adjudication-drift-clarified-by-architect` | 2 | stays 2 |
| `Stale-TODO-marker-after-work-complete` | 2 | stays 2 |
| `Board-meeting-attack-premise-needs-grep-verification` | 1 | stays 1 |
| `User-WONTFIX-after-design-dialogue` | 1 | stays 1 |
| `Doctrine-prediction-precision-improving-over-arc` | 4-cycle 0% streak | stays 4-cycle (5th 0% at Plan v1 §3 LOCK is forecast continuity; banks at closure-actual if 7 holds) |
| `Auditor-catches-doctrine-overlap-at-elevation-prep` | 1 (resolved at P0.S8 closure) | stays 1 |
| `Spec-internal-line-wrap-vs-substring-test-mismatch` | 1 (P0.S8) | stays 1 |
| OPTIONAL-Plan-v2 proof case (sub-rule under `### Zero-precision-items`) | 5 cases | stays 5 (closure-conditional 6th proof case pending if Plan v1 + closure clear cleanly) |
| `### Induction-surfaces-invariant-gaps` | 8 | stays 8 (D3 fires the doctrine at closure; bump 8 → 9 — invariant-coverage-gap surfaced at Phase 0 + closed at D3 in same cycle) |

---

## §9. Open questions for auditor (0)

No new open questions. Plan v1 absorbs all 4 PIs proactively per architect leans Q1-Q4 (auditor-adjudicated at Phase 0 verdict). Architect prediction: **APPROVED 0 items → ship to developer per OPTIONAL-Plan-v2 path (6th absorbed sub-rule proof case)**.

---

## §10. Implementation handoff readiness

**Developer contract:**
- **Scope:** D1 + D2 + D3 + D4 per §2.1-§2.4.
- **Estimated effort:** 2-3 hours (SMALL-band single-cycle; 1 function delete + 2 docstring updates + 2 test rewrites + 2 method-body wraps + 1 test-helper extension + 1 CLI flag addition).
- **Files touched (Python):**
  - `audit_person.py` (D1 — 2 line edits at line 17 + 79)
  - `core/audit.py` (D1 — docstring edit at line 5 + DELETE function at line 68-89)
  - `core/brain_agent.py` (D2 — 2 method-body wraps at line 3329 + line 3379)
  - `delete_person.py` (D4 — full rewrite ~50 LOC)
  - `person_lifecycle.py` (D4 — add `compute_delete_preview` helper ~40 LOC)
  - `tests/test_pipeline.py` (D1 — DELETE test at 8972 + REWRITE test at 8993)
  - `tests/test_faiss_atomicity_invariants.py` (D3 — extend scan surface ~10 LOC)
  - NEW `tests/test_p0_s9_helper_scripts.py` (7 anchors)
- **Files touched (docs):**
  - `KARAOS_KNOWLEDGE.md` (D1 — DELETE section at 1696-1701 + 1-line pointer in audit_gallery section above)
- **Phase 1 (~30 min)**: D1 redirect at audit_person.py + DELETE core/audit.py::repair_gallery + obsolete test cleanup + KARAOS_KNOWLEDGE.md docstring update. tsc / pytest verification.
- **Phase 2 (~30 min)**: D2 explicit transaction wrap on 2 BrainDB methods. pytest verification.
- **Phase 3 (~30 min)**: D3 inverse-check scan surface extension. pytest verification (the existing inverse-check test must still pass).
- **Phase 4 (~45 min)**: D4 `delete_person.py` rewrite + `compute_delete_preview` helper + 7 source-inspection tests in `tests/test_p0_s9_helper_scripts.py`.
- **Phase 5 (~30 min)**: §2.5 deliberate-regression confirmations (a/b/c/d/e all must fire correctly).
- **Phase 6 (~30 min)**: closure narrative + 5-surface landing + memory bankings + architect closure-audit.

---

## §11. Open invariants for Plan v1 to enumerate

1. **D1 redirect invariant** — `audit_person.py` calls `db.prune_outlier_embeddings(person_id)` AND no production caller of `core/audit.py::repair_gallery` survives.
2. **D2 explicit-transaction invariant** — `delete_person_data` + `prune_shadows_mentioning` bodies sit inside `with self.transaction():` blocks; no trailing `_conn.commit()`.
3. **D3 inverse-check coverage invariant** — scan surface covers `core/*.py` (top-level glob) with `_SCAN_EXCLUDE` allowlist for vendored subdirs.
4. **D4 default-deny invariant** — `delete_person.py` with neither `--dry-run` nor `--confirm` exits 1 with error message.
5. **D4 --dry-run preview invariant** — `compute_delete_preview` is READ-ONLY (no commits; SELECT counts only).
6. **No-side-effect-in-Phase-0 invariant** — Phase 0 audit landed with zero production code changes.

---

## §12. No closure-conditional doctrine elevation candidate at P0.S9

Unlike P0.S8 (which had the `Plan-v2-optional` doctrine elevation candidacy), P0.S9 has NO new doctrine elevation candidate at closure. Reasoning:

- Sub-pattern A 9th instance bumps `### Phase-0-catches-wrong-premise` existing-doctrine count (8 → 9), not a new doctrine.
- `### Induction-surfaces-invariant-gaps` 9th instance bumps existing-doctrine count (8 → 9), not new doctrine.
- `Plan-v1-Pass-2-grep-undercount` 4th instance still below 5+ elevation threshold (operational rule extension candidate, not standalone doctrine).
- OPTIONAL-Plan-v2 sub-rule already absorbed at P0.S8 closure.

P0.S9 is a routine SMALL-band cycle under matured discipline. No elevation event. Doctrine library stays at 6 numbered doctrines.

---

**End of Plan v1.** Ready to forward to auditor.

**Architect prediction:** **APPROVED 0 items → ship to developer per OPTIONAL-Plan-v2 path** (6th proof case under absorbed sub-rule; matches the 5 prior proof cases' clean pattern).
