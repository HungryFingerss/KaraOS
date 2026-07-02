# Developer — Coding Standards

The written standards, most of them CI-enforced (the enforcement file is named where one exists).

## The absolutes
- **No hardcodings, no predefined behavioral rules** — decisions belong to the brain (Jagan's standing project rule). Engine code provides mechanisms and floors; behavior is data (profiles, packs, flows) or LLM judgment.
- **ALL constants → `core/config.py`** — no magic numbers in decision logic (routing thresholds, bands, staleness budgets all have named constants). Enforced culturally + by review; the SB.6 staleness constant and SB.7 band constants are the pattern.
- **No silent `except: pass`** — every broad handler is annotated (`# RACE:`, `# CLEANUP:`, `# OPTIONAL:`) or logs; `except: return <falsy>` is the same swallow class. *Enforced: `tests/test_silent_except_invariant.py` (AST, incl. the falsy-return extension that found the pyannote-subprocess silent-None).*
- **No production `assert`** — raise typed errors. *Enforced: `tests/test_no_production_assert.py`.*
- **No wall-clock in deadline math** — `time.monotonic()` for elapsed/deadline; `time.time()` only for wall-clock semantics, `# WALLCLOCK:`-annotated; paired write/read sites use the SAME clock. *Enforced: `tests/test_no_walltime_deadline_math.py` + `tests/test_clock_consistency_paired.py` (auto-derived paired-clock invariant). Provenance: three real production bugs (cache TTL never expiring; the vision-watchdog 1.78e9s staleness).*
- **No raw `self._http.post` to the chat endpoint outside `_call_llm_chat`** (board §8.2) — the shared helper owns retry/backoff/shape-validation; migrating agents onto it repeatedly surfaced silent ReadTimeouts.
- **Fail-closed defaults everywhere** — privileges default-deny (`TOOL_PRIVILEGES`); missing `prior_person_type` → `"stranger"`; a physical renderer without a safety gate refuses to construct; an unknown persona/pack/profile id fails LOUD, never falls back silently.
- **Blocking I/O → `loop.run_in_executor`**; heavy GPU inference → the `heavy_worker` subprocess pools; never block the asyncio loop.

## Structure & layering
- **Layering direction**: `flows → runtime → core`; never import pipeline from below; no reaching into private internals across layers (`db._conn`, `_brain_orchestrator._brain_db` class of violations). *Enforced: `tests/test_layering_invariants.py` (FORBIDDEN_LAYERING_ACCESSES).* Expose owned state via property (read-only) or method (side-effecting) — don't refactor properties into `get_X()`.
- **Store pattern**: module-level mutable state lives in typed Stores (`Store` ABC) with async mutators, sync `peek_*` reads, `reset()`, paired-write atomicity. *Enforced: `tests/test_p06_store_invariants.py` + schema/inverse-check files.*
- **Paired cross-storage writes** (SQL+FAISS, brain.db+Kuzu): SQL-first, sentinel-marked, boot-reconciled; every paired-write method is in the enumerated tuple WITH an inverse check. *Enforced: `tests/test_faiss_atomicity_invariants.py`, `tests/test_kuzu_atomicity_invariants.py`.* The inverse-check rule generalizes: **every enumerated-set invariant ships with its inverse** (everything matching the pattern IS in the set) — the forward check alone let `prune_outlier_embeddings` ship broken.
- **Schema changes = versioned migrations** (the 5-tuple: version, description, apply, verify_post, verify_present) — never inline ALTERs. *Enforced: `tests/test_schema_migrations.py` structural scans.*
- **Registries over lists**: capabilities register with descriptors (agents SB.3, blocks SB.4, personas SB.8, tools/sensors/renderers/flows per the SB.9 design). Derived views are regenerated, never hand-maintained (the `_KNOWN_TOOL_NAMES` rule); `re.escape` any name interpolated into a regex (the closed-channel discipline).
- **Secrets**: values never interpolated into prints/logs; env reads centralized in config (allowlisted exceptions documented). *Enforced: `tests/test_secrets_invariants.py`; detect-secrets pre-commit + TruffleHog CI.*
- **SPDX headers** on every file (vendored trees excluded by policy). *Enforced: `tests/test_spdx_headers_invariant.py`.*
- **Vendored code**: pinned SHA, `trust_remote_code=False`, licenses preserved, supply-chain locked (`core/_florence2/`, `core/_minifasnet/` pattern).

## Honesty in behavior
- Perception uncertainty surfaces as hedges, never confident fabrication (the SB.6 hedge contract; the object-context injection rules).
- Degradation is observable: watchdogs, degraded flags, health-line fields, actionable operator alerts (recovery steps inline, never "see the docs").
