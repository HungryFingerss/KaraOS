# Pre-P1 Bundle 2 — Developer Phase 4 Handoff (2026-05-28)

**Status**: Plan v3 RATIFIED CLEAN by auditor 2026-05-28. Phase 4 GREENLIT.
**Cycle shape**: 5-artifact (Phase 0 + Plan v1 + Plan v2 + Plan v3 + closure)
**Scope**: 202 in-scope files (EXCLUDING `core/_minifasnet/*.py` per PI #3 absorption)
**Concurrent deliverable**: Bundle 2.X (`core/_minifasnet/LICENSE` MIT text — ship in same commit per Path α user adjudication)

---

## §1 Source-of-truth artifacts

Read these before starting (in order):

1. **Plan v3** (`tests/pre_p1_bundle2_governance_plan_v3.md`) — authoritative; absorbs PI #3 vendored MIT exclusion
2. **Plan v2** (`tests/pre_p1_bundle2_governance_plan_v2.md`) — file-count drift absorption (204 from ~260)
3. **Plan v1** (`tests/pre_p1_bundle2_governance_plan_v1.md`) — PI #1 + PI #2 absorptions
4. **Phase 0 audit** (`tests/pre_p1_bundle2_governance_audit.md`) — Q-answers + initial scope

Plan v3 supersedes prior plans on every numerical / scope detail. Treat earlier plans as historical context only.

---

## §2 Shipping order (Q6 RATIFIED — UNCHANGED across all 3 plans)

**D1 → D2 → D3 → D4 → D5 → D7 → D6 → Bundle 2.X**

Each step lands as its own commit. Bundle 2.X (MIT LICENSE) ships as the final commit before the closure-audit verdict-forwarding step.

---

## §3 D-decisions (verbatim content from Plan v1 §2)

### D1 — `LICENSE` (project root)

Apache License 2.0 verbatim text from https://www.apache.org/licenses/LICENSE-2.0.txt. ~11 KB. Filename `LICENSE` (no extension). NOT caught by `.gitignore` `/*.md` rule (no whitelist needed).

### D2 — `NOTICE` (project root)

Filename `NOTICE` (no extension). Content (verbatim per Q1 RATIFIED):

```
KaraOS
Copyright 2025-2026 The KaraOS Authors

This product includes software developed at HungryFingerss/Cognitive-System
(https://github.com/HungryFingerss/Cognitive-System).

Portions of this software are derived from:
- pyannote.audio (MIT License) — fork at HungryFingerss/pyannote-audio with dog-ai patches
- speechbrain (Apache License 2.0) — fork at HungryFingerss/speechbrain with dog-ai patches
- MiniFASNet (MIT License) — vendored at core/_minifasnet/ (model architecture from minivision-ai/Silent-Face-Anti-Spoofing)
```

NOT caught by `/*.md` rule. No whitelist needed.

### D3 — `GOVERNANCE.md` (project root)

5 required-content checkpoints (per A3 anchor):
1. **Philosophy** — Layer D cognitive runtime middleware positioning + open-source-builder-first stance
2. **BDFL** — current phase (Phase 1): Jagannivas as BDFL; explicit naming
3. **Decision-process** — RFC-via-issue → public discussion → BDFL adjudication
4. **Contributor expectations** — CLAUDE.md as project conventions source; strict-mode discipline reference
5. **Escalation** — disputes go to BDFL; future Phase 2/3 evolution path

**3-phase evolution path explicit**:
- **Phase 1** (current): BDFL — Jagannivas as sole adjudicator
- **Phase 2** (trigger: 3+ regular contributors): BDFL + 2-3 Maintainers + Committers (3 regular contributors threshold)
- **Phase 3** (trigger: 10+ committers): PEP-8016-style Steering committee

### D4 — `CODE_OF_CONDUCT.md` (project root)

Contributor Covenant 2.1 verbatim from https://www.contributor-covenant.org/version/2/1/code_of_conduct/. Customizations (per Q3 RATIFIED):
- Replace `[INSERT CONTACT METHOD]` → `jagannivas.001@gmail.com`
- Replace `[community]` → `KaraOS`
- Preserve "Version 2.1" marker (A4 anchor verifies)

### D5 — `CONTRIBUTING.md` (project root)

Lightweight contribution guide, ~50-100 lines. Required sections (per A5 anchor):
1. **Clone + install** — cross-reference `SETUP.md`
2. **Run tests** — `pytest` (full suite); link to CLAUDE.md test-count discipline
3. **Submit PR** — branch naming, commit message style, reviewer assignment
4. **Strict-mode discipline reference** — cross-reference CLAUDE.md Architectural Disciplines section
5. **CLAUDE.md as project conventions source** — explicit mention

### D6 — SPDX headers across 202 files + `.gitignore` whitelist update

**Mechanical-script**: NEW file `tools/add_spdx_headers.py`.

**Script contract** (per Plan v3 §2):

```python
"""Apply SPDX-License-Identifier + SPDX-FileCopyrightText headers to in-scope KaraOS Python + workflow files.

Idempotent: re-runs report 0 modifications.

Excludes vendored MIT-licensed paths per PI #3 (Plan v3 absorption 2026-05-28). Vendored MIT
compliance handled at directory level by Bundle 2.X (core/_minifasnet/LICENSE).

SPDX scope: 202 files = core/ (47, EXCLUDING _minifasnet/) + 4 top-level production scripts +
tools/ (6) + bootstrap/classifier/ (10) + tests/ (131) + .github/workflows/ (4).

Per REUSE Software spec semantics, SPDX-License-Identifier declares the file's actual license.
Uniform Apache-2.0 application to MIT-licensed vendored code would either misrepresent the
license, assert unauthorized sublicensing, or create ambiguous declaration. Hence EXCLUDED_PATHS.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

EXCLUDED_PATHS = ("core/_minifasnet/",)  # PI #3 absorption — vendored MIT compliance via Bundle 2.X

HEADER_PYTHON = '''# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
'''

HEADER_YAML = '''# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
'''

# ... script body ...
```

**Header placement (Q8 RATIFIED)**:
- `.py` files: AFTER module docstring (closing `"""`)
- `.yml` files: line 1 (after shebang if present, before any `name:` directive)

**Header insertion rules**:
1. Detect existing SPDX header (idempotency check — re-runs skip)
2. Detect module docstring position (Python only); insert 2-line header after closing `"""`
3. If no module docstring, insert 2-line header at line 1
4. For `.yml`: insert at line 1 (no docstring convention)
5. **EXCLUDED_PATHS check**: if file path starts with any excluded prefix, log `[SPDX] EXCLUDED (vendored MIT): {path}` and skip. Tally excluded count at exit.
6. Report added/skipped/excluded counts at exit

**Plus `.gitignore` update**: append 3 whitelist negations after the `/*.md` line:
```
!/GOVERNANCE.md
!/CODE_OF_CONDUCT.md
!/CONTRIBUTING.md
```

Idempotent — check for existing lines before adding.

### D7 — `README.md` append

Append at README.md tail (one section):

```markdown
## License & Governance

KaraOS is licensed under the **Apache License 2.0** (see [LICENSE](LICENSE) and [NOTICE](NOTICE)).

Governance model documented in [GOVERNANCE.md](GOVERNANCE.md). Contributor onboarding in [CONTRIBUTING.md](CONTRIBUTING.md). Community standards in [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
```

A7 anchor verifies 4 doc links + "Apache License 2.0" mention.

### Bundle 2.X (concurrent with Bundle 2 closure per Path α adjudication 2026-05-28)

New file: `core/_minifasnet/LICENSE`

Content: verbatim MIT text from upstream `minivision-ai/Silent-Face-Anti-Spoofing/LICENSE`:

```
MIT License

Copyright (c) 2020 Minivision

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OF OTHER DEALINGS IN THE
SOFTWARE.
```

Verify against upstream source before commit. Closes REUSE-tooling "missing license info" flag at directory level.

---

## §4 §0 NEW commitment EXTENSION (Bundle 1 + Plan v3 carry-forward)

**MANDATORY at Phase 4 pre-implementation, BEFORE invoking `tools/add_spdx_headers.py`**:

Run Pass-3 grep verifying both:

1. **File-count consistency vs Plan v3 estimate (202)** — per-bucket grep:
   - `core/*.py` excluding `_minifasnet/*.py` = 47
   - Top-level (`pipeline.py` + `enroll.py` + `delete_person.py` + `audit_person.py`) = 4
   - `tools/*.py` = 6
   - `bootstrap/classifier/*.py` = 10
   - `tests/*.py` = 131
   - `.github/workflows/*.yml` = 4
   - **TOTAL = 202**

2. **License-correctness per file/directory** — verify NO file in the 202-file in-scope list has a non-Apache-2.0-compatible license. Specifically:
   - `core/_minifasnet/*.py` — already excluded; verify EXCLUDED_PATHS catches them
   - No other vendored code in the in-scope buckets (confirmed at Phase 0 §2 D2 — only pyannote + speechbrain forks + MiniFASNet are vendored, and the forks live in pip packages, not in-tree)

**IF file-count drift > ±10% OR license-correctness anomaly surfaces** → STOP and raise back to architect for Plan v4 absorption. Same rollback discipline as Plan v2 absorption.

**IF clean** → proceed to Phase 4 implementation.

---

## §5 A6 parametrize anchor — test file shape

Plan v3 A6 = 202 file fan-out + 3 `.gitignore` whitelist checks = **205 pytest collections**.

Test file: `tests/test_spdx_headers_invariant.py` (NEW)

**Shape**:

```python
"""A6 anchor — structural parametrize across 202 in-scope SPDX files + 3 .gitignore whitelist lines.

PI #3 absorbed at Plan v3: core/_minifasnet/*.py EXCLUDED per vendored MIT compliance.

A8 STRENGTHENING locks EXCLUDED count = 2 invariant.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import pathlib
import pytest

# 202-file in-scope list (locked at Plan v3 §1.2)
IN_SCOPE_FILES: list[str] = [
    # core/ excluding _minifasnet/ (47 files)
    # ... enumerate
    # Top-level (4)
    "pipeline.py", "enroll.py", "delete_person.py", "audit_person.py",
    # tools/ (6) ...
    # bootstrap/classifier/ (10) ...
    # tests/ (131) ...
    # .github/workflows/ (4) ...
]

# Vendored MIT exclusions (PI #3)
EXCLUDED_PATHS: tuple[str, ...] = ("core/_minifasnet/",)

WHITELIST_LINES: list[str] = [
    "!/GOVERNANCE.md",
    "!/CODE_OF_CONDUCT.md",
    "!/CONTRIBUTING.md",
]

@pytest.mark.parametrize("path", IN_SCOPE_FILES)
def test_a6_file_has_spdx_header(path: str) -> None:
    """A6 — every in-scope file has SPDX-License-Identifier + SPDX-FileCopyrightText."""
    content = pathlib.Path(path).read_text(encoding="utf-8")
    assert "SPDX-License-Identifier: Apache-2.0" in content, f"{path} missing SPDX-License-Identifier"
    assert "SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors" in content, f"{path} missing SPDX-FileCopyrightText"


@pytest.mark.parametrize("line", WHITELIST_LINES)
def test_a6_gitignore_whitelist_present(line: str) -> None:
    """A6 — .gitignore contains required whitelist negations for governance .md files."""
    content = pathlib.Path(".gitignore").read_text(encoding="utf-8")
    assert line in content, f".gitignore missing whitelist line: {line}"


def test_a6_excluded_paths_not_in_scope() -> None:
    """A6 inverse-check — vendored MIT files NOT in IN_SCOPE_FILES list (PI #3 absorption)."""
    for path in IN_SCOPE_FILES:
        for excluded_prefix in EXCLUDED_PATHS:
            assert not path.startswith(excluded_prefix), \
                f"PI #3 absorption violation: {path} matches EXCLUDED_PATHS prefix {excluded_prefix}"
```

---

## §6 A8 STRENGTHENED anchor — script idempotency + exclusion invariant

Test file: `tests/test_spdx_script_idempotency.py` (NEW)

```python
"""A8 STRENGTHENED — tools/add_spdx_headers.py idempotency + EXCLUDED count = 2 invariant.

PI #3 absorption (Plan v3 2026-05-28): vendored MIT exclusion contract verified across runs.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import subprocess
import sys


def test_a8_script_idempotent_and_exclusion_invariant() -> None:
    """A8 — running tools/add_spdx_headers.py twice: 2nd run modifies 0 files + EXCLUDED count = 2 on both runs."""
    # First run (assumed to have already executed at Phase 4 implementation time)
    # Second run — assert 0 modifications + EXCLUDED count = 2
    result = subprocess.run(
        [sys.executable, "tools/add_spdx_headers.py"],
        capture_output=True, text=True, check=True,
    )
    output = result.stdout
    assert "Added: 0" in output, f"A8 idempotency violation: {output}"
    assert "Excluded: 2" in output, f"A8 EXCLUDED count invariant violation (PI #3): {output}"
```

---

## §7 5/5 deliberate-regression confirmations (`### Induction-surfaces-invariant-gaps` discipline)

After Phase 4 implementation, run these 5 deliberate regressions (revert each cleanly after fire-confirmation):

1. **(a) Delete `LICENSE` file** → A1 fires (LICENSE absent at repo root)
2. **(b) Delete `NOTICE` file** → A2 fires (NOTICE absent)
3. **(c) Remove `EXCLUDED_PATHS = ("core/_minifasnet/",)` from `tools/add_spdx_headers.py`** → A8 fires (EXCLUDED count != 2; PI #3 invariant lock)
4. **(d) Drop one of 3 whitelist negations from `.gitignore`** → A6 fires (whitelist line missing)
5. **(e) Strip SPDX header from one in-scope file** → A6 fires (parametrize hit fails for that path)

Document each regression result in the closure narrative under "5/5 deliberate-regression confirmations passed cleanly".

---

## §8 Closure narrative requirements

When Phase 4 complete + all 8 anchors green + 5/5 regressions passed cleanly:

1. **Append closure entry** to `CLAUDE.md` banner using Plan v3 §6 paste template (substitute actual closure date)
2. **Update test count** at top of CLAUDE.md banner (current ~3329 + 205 new collections from A6 + 1 from A8 = ~3535; subtract any incidental adjustments at Phase 5 ripple-fix time per locked LINE-REF-DRIFT preventive discipline)
3. **Update `to_be_checked.md`** with Bundle 2 entry (deferred-canary strategy 36th application)
4. **Path C grep-verify** at closure-narrative drafting:
   - Production code surfaces (5 new files + 202 SPDX headers + .gitignore + README + `tools/add_spdx_headers.py`)
   - `core/_minifasnet/LICENSE` Bundle 2.X concurrent commit landed
   - Memory file paths (no new memory files this cycle expected — CROSS-PATH-SYNC-OMISSION no-op)
   - `to_be_checked.md` Bundle 2 entry via PowerShell fresh-disk read (DEFERRED-CANARY-ENTRY-OMISSION preventive)
5. **Forward closure-audit findings to auditor** for explicit ratification BEFORE declaring Bundle 2 CLOSED (7th-cycle routinization; Bundle 1 closure precedent + P0.R10-P0.S10 history)
6. **Enumerate 9 preventive disciplines applied** for multi-discipline preventive convergence elevation event preservation:
   1. LINE-REF-DRIFT preventive (Plan v1)
   2. CROSS-PATH-SYNC-OMISSION preventive commitment
   3. DEFERRED-CANARY-ENTRY-OMISSION grep-verify commitment
   4. Closure-audit verdict forwarding commitment (7th-cycle routinization)
   5. CODE-TEMPLATE-MISIDENTIFICATION preventive (Apache + MIT text verbatim)
   6. Developer Pass-3 grep at Phase 4 pre-implementation (§0 NEW commitment Bundle 1 carry-forward)
   7. §0 NEW catching-layer ACTIVATED as designed (Plan v2 file-count drift)
   8. BIDIRECTIONAL Pass-3 file-count verification at Plan v2
   9. BIDIRECTIONAL license-precision audit at Plan v3 (PI #3 absorption + EXCLUDED_PATHS architectural defense)

---

## §9 Closure-projection Q5 reading

Q5 LOCK at mid 8 anchors. NARROW band [6.8, 9.2]. Honest closure-actual reporting per `Explicit-closure-honest-count-commitment`:

- IF closure-actual = 8 exact → `Doctrine-prediction-precision-improving-over-arc` 11th consecutive 0%-streak rebuild banks
- IF closure-actual ∈ {7, 9} → `### Phase-0-granular-decomposition` 31 → 32 supporting; streak interrupted
- IF closure-actual ∈ {6, 10} → SLIGHT-DRIFT-DOWN/UP within ±30%; doctrine HOLDS at 31; streak interrupted
- IF closure-actual ≤5 OR ≥11 → FALSIFICATION-WATCH activates; closure-audit names root cause

Anchor enumeration: A1 (LICENSE) + A2 (NOTICE) + A3 (GOVERNANCE.md) + A4 (CODE_OF_CONDUCT.md) + A5 (CONTRIBUTING.md) + A6 (SPDX 205-collection parametrize) + A7 (README append) + A8 (script idempotency STRENGTHENED). Total = 8 logical anchors UNCHANGED across all 3 plans.

---

## §10 Standing by

Phase 4 ready to execute. Implementation order: D1 → D2 → D3 → D4 → D5 → D7 → D6 → Bundle 2.X → tests → 5/5 regressions → closure-audit forwarding to auditor.

Pre-implementation step: run §0 NEW commitment EXTENSION Pass-3 grep (file-count + license-correctness verification). If clean, proceed.

On Phase 4 completion: forward closure-audit findings + 9-discipline preventive convergence enumeration to auditor for explicit ratification per locked 7th-cycle routinization discipline.

---

**Filed**: 2026-05-28
**Architect**: Claude
**For**: Developer Phase 4 implementation
**Prior artifact**: `tests/pre_p1_bundle2_governance_plan_v3.md` (RATIFIED CLEAN; PI #3 absorbed via Option A EXCLUDE; user adjudication Path α concurrent Bundle 2.X locked)
