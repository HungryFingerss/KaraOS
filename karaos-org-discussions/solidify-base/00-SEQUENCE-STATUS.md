# Solidify-Base — Sequence & Status (live tracker)

**Resequenced 2026-06-05 (Jagan):** monolith decomposition (**P1.A1**) moved to run **right after SB.1**, *before* the multi-purpose work — so the config/agent/harness cycles (and the eventual supermarket + robotics clones) all land on clean, modular files instead of 9k-line monoliths. The board's original order put decomposition last; Jagan moved it to 2nd.

## Order of operations

1. **SB.1 — Demolition + git cleanliness** — ✅ **CLOSED 2026-06-05** (architect Layer-3 PASS; independent full-suite **3820/0** on the CUDA box & **3814/0** on the dev box; 4 atomic commits `8e6d71e`→`76d3af5` on `main`, **UNPUSHED** per the D4.3 HARD GATE). Removed the AGPL YOLO stack + dead flags (incl. the `CROSS_PERSON_EXCERPTS` cascade) + 10 one-shot tools + dead artifacts; untracked all committed PII from HEAD + gitignored under env-overridable `KARAOS_INSTANCE_MODE` (`git ls-files faces/ data/` = only the classifier seed). D1 deviation `_infer_location_zone` KEPT (non-YOLO geometry helper, aliased-import live) — empirical RED ratified. **Deferred to P1.A1:** the `tests/*.md` relocation (a hard path-assertion + ~15 refs → folds into the P1.A1 tests/ reorg). Cosmetic stale-count sweep noted (`room_orchestrator.py:3` / `test_p0_s7_dd.py:377` say '7' → now 6; `test_bundle3_anchors.py:30/32` retired-script provenance; P0.S5 '17').
2. **P1.A1 — Monolith decomposition** — ⏭ **NEXT.** Behavior-neutral split of the giant files into per-concern modules **along the engine/app seam** (the reusable runtime vs the companion app). Current sizes: `pipeline.py` ~9,040, `brain_agent.py` ~8,905, `test_pipeline.py` ~16,547 (also move it root → `tests/`), `core/db.py` ~2,108, `core/brain.py` ~3,390. Mechanical extraction only — **zero behavior change.** Gets its own Phase 0 (map the seams) → Plan v1 → … → Layer-3.
3. **🐦 CANARY GATE (Jagan).** A thorough full-system canary after P1.A1. Because the decomposition is behavior-neutral, the canary must show **zero behavior change** — that's the proof the split preserved behavior before any multi-purpose work begins.
4. **The multi-purpose work (all now on clean modules):** **SB.2** Config profile system (foundation) → **SB.3** Agent registry → **SB.4** Harness → **SB.5** Identity/retention mode → **SB.6** Object detection (Florence-2) → **SB.7** Perception eval harness → **SB.8** Persona pack → **SB.9** Adapter seam (design-only).
5. **Push the solid base, and STOP.**

## After Solidify-Base (Jagan's plan)
Build **two clones in parallel** — the **automated supermarket** and the **robotics stack** — each a *profile + thin overlay* on the versioned base, never a code fork. The decompose-early order exists precisely so 2-clone maintenance + cross-stack bug-fixing happen on modular files.

## Why decompose-early (the resequence rationale)
- Doing config/agent/harness work on 9k-line files and splitting *later* does the hard work twice — the splits would re-thread all the new config wiring.
- Splitting **after** SB.1 means we split **less** (dead weight already removed).
- Modular, single-concern files make bug-finding + wrong-logic identification tractable — for Jagan reading the code *and* the architect/developer reasoning over it.
- P1.A1 is behavior-neutral, so the post-P1.A1 canary is a clean, unambiguous validation gate.

## Exit gate (unchanged — board §10)
Done when: profile loader + agent manifest + validator ship and companion-equivalence is green; prompt ≥40% smaller, zero bench regression; intent = one authority; AGPL/dead-flags/husks/duplicate-roster gone; PII out of the base; perception harness has a committed baseline; the supermarket wedge boots from a profile + thin flow with **zero `core/` diffs.** Then push and clone.
