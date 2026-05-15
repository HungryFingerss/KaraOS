# Silent-Except Policy — Dog-AI

Every `except (Exception | BaseException | bare): pass` handler in production
code **must** carry a co-located triage annotation.  This document explains why,
what the four allowed annotations mean, and how to pick the right one.

---

## Why this rule exists

A silent broad-except is a promise: "I thought about this failure mode and
decided swallowing it is correct."  Without a written explanation that promise
is invisible.  Future readers (including you six months from now) cannot tell
whether the swallow was:

- intentional and correct, or
- a lazy placeholder that silently hides a real bug.

The structural invariant test (`tests/test_silent_except_invariant.py`) enforces
that every such handler carries an annotation.  The test is PR-blocking: a new
unannotated handler will fail CI before it can merge.

---

## The four buckets

### Bucket A — Benign (two sub-labels)

These handlers are genuinely harmless.  The operation is either optional or
best-effort, and the failure path has a safe fall-through.

**`# CLEANUP:`** — resource teardown where failure is irrelevant.

```python
try:
    cap.release()
except Exception:
    pass  # CLEANUP: cap may already be released before reconnect
```

Use this when the only purpose of the block is freeing a resource (socket, file,
camera, DB connection) and a failure here cannot corrupt state.

**`# OPTIONAL:`** — genuinely optional operation where the program has a correct
fall-through if it does not run.

```python
try:
    _state_file.write_text(json.dumps(state))
except Exception:
    pass  # OPTIONAL: state-file absent or corrupt — caller gets offline default
```

Use this for metrics counters, state-file reads, prefetch operations, and
fire-and-forget background tasks that already have an explicit fallback path.

---

### Bucket B — Race condition (one label)

**`# RACE:`** — a known concurrency race where swallowing is the correct response.

```python
try:
    self._conn.execute("ROLLBACK")
except Exception:
    pass  # RACE: S65 _safe_commit no-active-transaction race — ROLLBACK raises if BEGIN EXCLUSIVE failed
```

The classic shape: operation A fails, operation B is the compensating action,
but B can also fail if A never started.  Swallowing B's failure is correct
because the error from A is already being handled or re-raised.

Requires: a comment that names the specific race, not just "race condition".

---

### Bucket C — Silent failure (must NOT use pass)

If an exception from this handler could cause silent data corruption, a
false-success signal, or undetected state divergence — do not swallow it.

**Required action:** propagate the exception, or at minimum log it before
swallowing.

The canonical P0.4 Bucket C case:

```python
# BEFORE (broken — swallowing Kuzu errors let schema upgrades silently half-succeed):
for stmt in ("DROP TABLE IF EXISTS RELATES_TO", "DROP TABLE IF EXISTS Entity"):
    try:
        self._conn.execute(stmt)
    except Exception:
        pass

# AFTER (fixed — errors propagate to _ensure_graph_sync(), preventing false version commit):
for stmt in ("DROP TABLE IF EXISTS RELATES_TO", "DROP TABLE IF EXISTS Entity"):
    self._conn.execute(stmt)
```

---

### Bucket D — Unknown (treat as Bucket C)

If you cannot determine whether a handler is Bucket A/B or C within the time
available — treat it as Bucket C.  Add logging and re-raise.  A missed Bucket A
is a slightly noisier log.  A missed Bucket C is a silent bug.

---

## Annotation placement

The annotation must appear on one of these three lines (the detector checks all
three):

```
end_lineno - 1   → pass line itself   (preferred)
except_lineno - 1 → the except: line
except_lineno - 2 → line immediately above except:
```

The most readable form is inline on the `pass` line:

```python
except Exception:
    pass  # RACE: ...
```

---

## Adding a new handler

1. Write the handler.
2. Classify it (A/B/C/D).
3. If A or B: add the annotation inline.
4. If C or D: propagate or log-and-re-raise; do not use `pass`.
5. Run `pytest tests/test_silent_except_invariant.py` locally — it will fail
   immediately if the annotation is missing.

---

## The bulk annotator (one-shot tool)

`tools/bulk_annotate_p04.py` adds `# TODO-P0.4: triage` to every unannotated
site.  It is a **one-shot migration tool**, not a workflow.  After running it,
triage each site and replace the placeholder with the correct annotation.
`# TODO-P0.4:` is **not** a permitted annotation — the invariant test will fail
if any site still carries it.

---

## Tooling reference

| Item | Location |
|---|---|
| Structural invariant test | `tests/test_silent_except_invariant.py` |
| Bulk annotator (one-shot) | `tools/bulk_annotate_p04.py` |
| Permitted annotations | `PERMITTED_ANNOTATIONS` in both files above |
| Allowlisted paths | `ALLOWLIST_PATHS` in both files above (`core/_minifasnet`) |
