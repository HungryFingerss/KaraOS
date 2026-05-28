> **CHAPTER 05 — Face/Voice Galleries** | Sourced from `everything_about_system.md` §36-46 (verbatim mechanical extraction per Plan v2 §1.6 section-number stability invariant).

---

## 36. FaceDB Architecture — SQLite Plus FAISS

### 36.1 The split

`FaceDB` is the single class that owns all identity-related persistence. It combines:
- **SQLite (WAL mode)** for the authoritative records — `persons`, `embeddings`, `voice_embeddings`, `conversation_log`, `silent_observations`, `visitor_log`, `system_identity`.
- **FAISS IndexFlatIP** for fast approximate nearest-neighbour search on face embeddings.

SQLite is the ground truth; FAISS is a derived index rebuilt from SQLite when the authoritative state changes. If FAISS is ever out of sync we can rebuild it without data loss; we cannot do the reverse.

### 36.2 Why SQLite WAL

- **WAL** (write-ahead log) allows concurrent readers while a writer is active. The dashboard reads `faces.db` while the pipeline writes to it.
- **ACID** guarantees. Every INSERT/UPDATE/DELETE either completes or leaves no trace.
- **Zero ops.** No server to start; no connection pool to manage. `sqlite3.connect(path)` just works.
- **Portable.** Same binary file on Windows and Linux. Same SQL dialect. Same recovery behaviour.

### 36.3 Why FAISS IndexFlatIP

- **Exact search.** IndexFlatIP enumerates all vectors. Not approximate. Good enough for ≤ 10k galleries; past that we'd migrate to IVF.
- **Simple math.** IP on L2-normalised vectors equals cosine similarity. We never call a distance function explicitly.
- **No training.** Unlike IVF which needs a training set, FlatIP works with any vectors.
- **GPU-ready** on Jetson — just swap `faiss-cpu` for `faiss-gpu`.

### 36.4 Thread safety

Every FAISS access is guarded by `self._index_lock` (`threading.RLock`). Session 35 Bug-13 added this. Without it, concurrent `recognize()` and `add_embedding()` calls could interleave between "prepare query" and "search" with disastrous results.

### 36.5 Connection discipline

Every `FaceDB` instance holds exactly one SQLite connection (`self._conn`). It is created with `check_same_thread=False` because we call it from both the main event loop and from executor threads. All mutations go through `FaceDB` methods; nothing outside the class ever constructs a statement against `faces.db`.

## 37. Embedding Storage and Diversity Gate

### 37.1 The table

```sql
CREATE TABLE embeddings (
    id         INTEGER PRIMARY KEY,
    person_id  TEXT NOT NULL,
    vector     BLOB NOT NULL,          -- 512 × float32 little-endian
    captured_at REAL NOT NULL,
    source     TEXT NOT NULL,          -- enrollment, recognition_update, progressive_enroll
    quality    REAL,                   -- V1 score at write time
    FOREIGN KEY (person_id) REFERENCES persons (id) ON DELETE CASCADE
);
CREATE INDEX embeddings_person_id_idx ON embeddings(person_id);
```

### 37.2 `add_embedding(pid, emb, source) -> bool`

Returns True iff the embedding was written; False if the diversity gate rejected it.

```python
def add_embedding(self, person_id, emb, source, **kwargs) -> bool:
    with self._index_lock:
        assert source in VALID_EMBEDDING_SOURCES, f"unknown source {source!r}"

        # Anti-poisoning: recognition_update must clear centroid gate
        if source == "recognition_update":
            centroid = self._centroid_for(person_id)
            if centroid is not None:
                cos = float(np.dot(emb, centroid))
                if cos < SELF_UPDATE_CENTROID_MIN:
                    return False

        # Diversity gate — skip if too similar to an existing embedding
        existing = self._load_person_embeddings(person_id)
        if len(existing) >= N_INITIAL_FACE:  # post-enrollment regime
            for e in existing:
                if float(np.dot(emb, e)) > FACE_DIVERSITY_THRESHOLD:
                    return False

        # Cap check
        if len(existing) >= MAX_EMBEDDINGS:
            return False

        # Insert
        self._conn.execute(
            "INSERT INTO embeddings (person_id, vector, captured_at, source, quality) VALUES (?, ?, ?, ?, ?)",
            (person_id, emb.tobytes(), time.time(), source, kwargs.get("quality")),
        )
        self._conn.commit()

        # FAISS: add the same vector
        self._index.add(np.expand_dims(emb, 0).astype(np.float32))

        return True
```

### 37.3 Why diversity gating

Without it, a person sitting still facing the camera would accumulate 50 nearly-identical embeddings in a few minutes — wasted storage, no recognition improvement. The 0.92 cosine threshold means "this new crop is fundamentally similar to something already stored" and we skip the write.

First N_INITIAL_FACE=5 embeddings bypass the gate to give enrollment a solid baseline.

### 37.4 MAX_EMBEDDINGS cap

50 samples per person is the ceiling. Covers all reasonable angles. Past this, we stop adding. Without the cap, recognition latency grows linearly (FlatIP scans all); with the cap, worst-case FAISS search over 10 people × 50 = 500 vectors is sub-millisecond.

### 37.5 `source` values

`VALID_EMBEDDING_SOURCES = frozenset({"enrollment", "recognition_update", "progressive_enroll"})`. Any other string triggers the assert at `add_embedding`. Session 46 Finding E added this.

- `enrollment` — the initial capture during first_boot_flow or enrollment_flow.
- `progressive_enroll` — the gate-pass face captured for a stranger when they said the system name.
- `recognition_update` — self-update: a high-confidence recognition triggered storage of the new crop for gallery diversity. Requires anti-spoof pass.

## 38. Recognition with Adaptive Thresholds

### 38.1 `recognize(emb, threshold) -> (pid, name, score)`

```python
def recognize(self, emb, threshold) -> tuple[str | None, str | None, float]:
    with self._index_lock:
        if self._index.ntotal == 0:
            return None, None, 0.0
        D, I = self._index.search(np.expand_dims(emb, 0).astype(np.float32), k=1)
        score = float(D[0][0])
        if score < threshold:
            return None, None, score   # score returned even on miss
        idx = int(I[0][0])
        pid = self._idx_to_pid[idx]
        row = self._conn.execute("SELECT name FROM persons WHERE id = ?", (pid,)).fetchone()
        name = row[0] if row else None
        return pid, name, score
```

Returns (None, None, score) when no match — critically, score is still returned so the caller can decide what to do with a below-threshold match (e.g., flag as silent observation, log for debugging).

### 38.2 How threshold is derived per call

The pipeline calls with a threshold computed from V4 (adaptive_threshold based on quality score) plus a pool-depth penalty:

```python
_thresh = adaptive_threshold(quality, RECOGNITION_THRESHOLD)
if temporal_buffer.pool_depth(track_id) < 3:
    _thresh += 0.05   # less pool data → demand higher similarity
```

### 38.3 Why score is returned on miss

Two uses:
1. **Silent observation matching.** If a face is seen but below threshold (stranger), we check if they are similar to a previously-seen silent observation (SILENT_OBS_SIMILARITY=0.82). If so, update that observation; if not, create a new one.
2. **Debugging.** The log shows `[Vision] Background: score=0.234, below threshold 0.280`, which helps diagnose why a person isn't being recognised.

## 39. Temporal Embedding Buffer

`TemporalEmbeddingBuffer` (in `core/vision.py`) maintains a deque per `track_id` of the last 5 embeddings. `add_and_pool(track_id, emb)` appends and returns the mean of the current contents.

Keys are reset when a track dies (unmatched for SORT_MAX_AGE frames). Session 34 Bug-8 fix pruned `_last_raw` similarly to active SORT tracks to prevent memory growth.

The pool is deliberately simple — no weighting by quality, no outlier rejection. Mean-pool is a huge variance reducer on its own; adding sophistication for a 5-element buffer is over-engineering.

## 40. Gallery Poisoning Prevention

### 40.1 The incident — "uncle false match"

An uncle who visited Jagan's home triggered a recognition score of ~0.35 — above `RECOGNITION_THRESHOLD=0.18` (at the time) and above `SELF_UPDATE_THRESHOLD=0.32` (at the time). The system "recognised" him as Jagan and wrote a `recognition_update` with *his* face embedding to Jagan's gallery. Subsequent recognitions of the uncle matched *more* embeddings in Jagan's gallery. Feedback loop; gallery poisoned.

### 40.2 The fix (Session 51)

Four changes:

1. **`SELF_UPDATE_THRESHOLD` raised 0.32 → 0.45.** Anything below 0.45 is "merely similar" and not trusted for self-update.
2. **`SELF_UPDATE_CENTROID_MIN=0.55`** — a new check. The new embedding's cosine similarity to the person's gallery centroid must exceed this. Catches outliers at write time. An uncle's crop at 0.45 similarity to Jagan's *best* embedding might be at 0.32 to Jagan's *centroid* → rejected.
3. **`RECOGNITION_THRESHOLD` raised 0.18 → 0.28.** AdaFace IR101's stable EER region starts at 0.28, not 0.18.
4. **Anti-spoof required for `recognition_update`.** A photo-attack crop would pass the cosine gates (static photos look like the real person) but fail anti-spoof. Closes the attack loop.

### 40.3 Why centroid gate and not just best-match

Best-match gives a noisy signal — a single outlier embedding in the gallery can artificially pull up the score for unrelated crops. Centroid is the *stable* identity; requiring new crops to cluster near the centroid keeps the gallery drifting only along its natural distribution.

### 40.4 Why not stricter thresholds

We could have kept lifting thresholds but that harms recall on legitimate users with varying lighting and expressions. The combination of threshold + centroid + anti-spoof is the sweet spot between precision and recall.

## 41. Gallery Audit and Repair

### 41.1 `core/audit.py`

```python
def gallery_audit(person_id: str = None, sigma: float = 2.0) -> list:
    """For each embedding, compute cosine to the gallery centroid.
    Flag outliers (below mean - sigma × std).
    Returns [{id, person_id, cosine_to_centroid, flagged: bool}]."""
```

### 41.2 CLI tool

`audit_person.py <person_id>` prints a table of embeddings with their centroid cosines and flags. The operator can manually delete rows via SQLite if any are suspicious.

### 41.3 Dashboard integration

`/api/gallery-audit?person_id=...` returns the same data for browser display. The dashboard shows flagged embeddings with their face crop so the operator can visually confirm.

### 41.4 When to run

We don't run it automatically. The idea is: when something feels wrong (a known person isn't being recognised as reliably), audit their gallery. Flagged outliers are likely the cause. Delete them and the recognition restores.

In the future, an automatic audit could run in the dream loop once per week.

---
---

# Part VII — Voice and Speaker Identity

## 42. ECAPA-TDNN Speaker Embedding

### 42.1 Model

SpeechBrain `spkrec-ecapa-voxceleb` — the ECAPA-TDNN architecture trained on VoxCeleb. Input: raw waveform (16 kHz mono). Output: 192-dimensional L2-normalised embedding.

EER on VoxCeleb1-O is 0.80%, meaning at the equal-error threshold ~99.2% accuracy on speaker verification. We operate at a lower-recall, higher-precision threshold (`VOICE_RECOGNITION_THRESHOLD=0.25`) because false matches are much worse than missed matches in our setting.

### 42.2 Why not x-vector or d-vector

ECAPA outperforms both on short utterances. Voice samples in daily conversation average 3-8 seconds; short-utterance performance matters. ECAPA is also packaged as a single SpeechBrain class with pretrained weights, so integration is a one-liner.

### 42.3 Two torchaudio patches

`core/voice.py` contains patches for SpeechBrain's torchaudio backend detection that were broken on Windows. The patches are applied at module import time. Without them, ECAPA load fails.

## 43. Voice Gallery

### 43.1 The table

```sql
CREATE TABLE voice_embeddings (
    id                  INTEGER PRIMARY KEY,
    person_id           TEXT NOT NULL,
    vector              BLOB NOT NULL,   -- 192 × float32
    captured_at         REAL NOT NULL,
    source              TEXT NOT NULL,   -- voice_self_match, voice_face_verified
    confidence_at_write REAL,
    FOREIGN KEY (person_id) REFERENCES persons (id) ON DELETE CASCADE
);
CREATE INDEX voice_embeddings_person_id_idx ON voice_embeddings(person_id);
```

### 43.2 In-memory gallery

`pipeline._voice_gallery: dict[pid, np.ndarray]` — the mean embedding per person. `_voice_gallery_sizes: dict[pid, int]` — the number of embeddings that contributed to that mean.

Loaded at startup from DB via `db.load_voice_profiles()` and `db.load_voice_profile_sizes()`.

### 43.3 Update on new sample

`db.add_voice_embedding(pid, emb, source, confidence)` inserts a row. The pipeline then calls `db.load_voice_profile_for(pid)` to get the updated mean and stores it in `_voice_gallery[pid]`. Session 24 I2 made this a targeted update (one person) instead of reloading the whole gallery (much cheaper on large galleries).

### 43.4 MAX_VOICE_EMBEDDINGS cap

20 per person. Once reached, new additions can still happen but are gated by a diversity check (`VOICE_DIVERSITY_THRESHOLD=0.85`). In practice, most people stabilise at ~15 samples after a few conversations.

## 44. Voice Identification

### 44.1 `voice_mod.identify(audio, gallery, threshold) -> (pid, score)`

```python
def identify(audio, gallery, threshold):
    emb = _ecapa_embed(audio)   # 192-d L2-normalized
    best_pid, best_score = None, 0.0
    for pid, profile in gallery.items():
        score = float(np.dot(emb, profile))
        if score > best_score:
            best_pid, best_score = pid, score
    if best_score < threshold:
        return None, best_score
    return best_pid, best_score
```

Exhaustive search. Cheap — 192-d dot product × 10 people is nothing. No need for a FAISS index on voice.

### 44.2 Threshold choices

- `VOICE_RECOGNITION_THRESHOLD=0.25` — EER operating point. Below this, we say "unknown."
- `VOICE_SPEAKER_SWITCH_THRESHOLD=0.50` — min confidence to *open* a session for a different enrolled speaker. Identifying a voice is not the same as switching sessions; switching needs more evidence.

### 44.3 Routing consumes the result

`identify()` is called once per turn. The result feeds `_resolve_actual_speaker` which combines it with face evidence to produce the final routing decision. See §59.

## 45. Voice Self-Update

### 45.1 `_accumulate_voice(pid, audio, db, face_verified)`

This is the function that writes new voice samples to the gallery. It:

1. Extracts an embedding from `audio`.
2. Calls `_voice_accum_allowed(session)` to check Path A/B/C.
3. If allowed:
   - Decrements bootstrap_credits if that was the winning path.
   - Decides `source` (voice_face_verified if face_verified else voice_self_match).
   - Calls `db.add_voice_embedding(pid, emb, source, confidence)`.
   - Reloads `_voice_gallery[pid]` via `db.load_voice_profile_for`.
   - Updates `_voice_gallery_sizes[pid]`.
   - Logs `[Voice] Profile updated for {pid} (N/20 voice samples) [via {path}]`.
4. If refused:
   - Logs `[Voice] Refused accumulation for {pid}: {reason}`.

### 45.2 Why `face_verified` affects source

`voice_face_verified` means we know this voice belongs to this face because we saw the face at the time. Higher trust. `voice_self_match` means the voice profile self-matched; this is weaker evidence. Downstream could weight them differently (we don't yet; they both contribute equally to the mean).

## 46. Stale Stranger Voice Pruning

### 46.1 The problem

A stranger opens a voice session, says the system name, the engagement gate passes, we add a few voice embeddings under their `stranger_<uuid>` pid. They then leave and never come back. Their thin voice profile lingers and could false-match a new voice similarly.

### 46.2 `prune_stale_stranger_voice(days)`

Runs in the dream loop. Deletes `voice_embeddings` rows for strangers whose profile never reached `N_INITIAL_VOICE=5` samples and hasn't been updated in `STRANGER_VOICE_TTL_DAYS=3` days.

Session 54 Finding J split this into `find_stale_stranger_voice_ids(days)` (read-only) + `prune_stale_stranger_voice(days, ids=...)` (destructive) so the dream loop can evict the in-memory cache *first*, then delete rows — preventing a microsecond window where `voice_mod.identify` could match a stranger whose DB row was about to vanish.

---
---

# Part VIII — Session Management

