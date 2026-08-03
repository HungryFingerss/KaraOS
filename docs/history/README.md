# docs/history — the implementation record

Every cycle, phase, and closure that has shipped in KaraOS is written down
here. `CLAUDE.md` carries the **current** state; this directory carries the
**trail**.

## Why this directory exists

On 2026-07-30 `CLAUDE.md` had reached **1,029 KB, with a single 522 KB line**.
Claude Code truncates on load, so most of the file was never actually read in
any session — a source of truth that cannot be read is not one. The same
silent-truncation failure had hit the memory index at 24 KB the same day, 40×
smaller and caught only because the runtime warned.

The narrative moved here; `CLAUDE.md` dropped to ~153 KB and now opens with a
current-state block placed **above** the bulk so it always loads. Nothing was
deleted. Line conservation was verified exactly (1,611 kept + 305 extracted =
1,916 original).

Precedent: Pre-P1 Bundle 1 did the same surgery on
`everything_about_system.md` (9,214 lines → 19 chapters under
`docs/architecture/` + a thin redirect).

## THE RULE — write here whenever anything is implemented

**Every implementation gets an entry here, at the time it lands — not at the
end of the cycle.** A phase closes, a fix lands, a defect is found, a ruling is
made: it goes in the active cycle file below, same session. This is not
optional bookkeeping; it is the only reason anyone (including a future session
with no memory of this one) can reconstruct why the system is shaped the way it
is.

**What an entry must carry**, because these are the fields that turn out to
matter months later:

1. **What changed** — files/functions touched, not just prose.
2. **Commit hash** — so the claim is checkable against the tree.
3. **Why** — the defect or requirement that forced it. A change without a
   reason is unmaintainable.
4. **Evidence** — the measurement, test, or RED proof that says it works, and
   the honest state if it is unproven.
5. **What was decided against, and why** — the discarded option is often more
   informative than the chosen one.
6. **Known limitations** — stated, never omitted. Anything deferred gets named
   as deferred.

**Rules of the record:** never rewrite history to look cleaner. Corrections are
appended with the correction visible, because a wrong diagnosis that was caught
is itself part of the engineering record. Numbers are quoted with the hardware
and configuration that produced them.

## Layout

| file | contents |
|---|---|
| `SB2-LLM-LOCAL-FLIP.md` | **ACTIVE cycle** — local-primary brain (Ollama gpt-oss:20b), Together.ai secondary |
| `CLOSURE-NARRATIVES.md` | Per-cycle closure narratives through 2026-07-06: SB.1 demolition, the 5 Pre-P1 bundles, the P0.R resilience arc (14 cycles), the P0.S/P0.B tracks, canaries #1-#4, the coverage-to-100 campaign |
| `COMPLETED-SESSIONS.md` | Session-by-session table, Sessions 1-122 (2026-03 → 2026-04) |
| `BUG-AUDIT-2026-04-10.md` | The full 2026-04-10 audit (B1-B8, A1-A8, G3-G6, I2-I5) — all resolved |
| `BOARD-BUG-TRACK.md` | Board-bug remediation track, original 10-bug scope — CLOSED 2026-05-21 |
| `LICENSE-CHANGE-2026-08-03.md` | Apache-2.0 → proprietary source-available; snapshot rule stated; repo stays public through the YC window |

New cycle → new file, named for the cycle, linked in this table. Detailed
specs stay in `rule book/cycle-specs/`; this directory is the record of what
actually shipped and why.
