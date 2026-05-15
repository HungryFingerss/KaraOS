"""
core/classifier_db.py — Classifier scenarios DB (Spec 1).

Schema, migrations, audit log, and read/write API for the pure-graph
classifier's scenario store. Lives at data/classifier_scenarios.db,
separately from faces.db / brain.db. Factory reset must NOT touch this DB.

All scenarios are abstracted (PII stripped) at write time. Hot-path
classification (Spec 2) reads via query_nearest().
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from core.config import (
    CLASSIFIER_ABSTRACT_RULE_VERSION,
    CLASSIFIER_AUDIT_LOG_PATH,
    CLASSIFIER_DB_PATH,
    CLASSIFIER_EMBEDDING_MODEL_ID,
    CLASSIFIER_SNAPSHOT_DIR,
)


SCHEMA_VERSION = 2
SEED_VERSION = 1

# Audit event vocabulary (kept loose at the DB layer — strings, not enum,
# so future event types don't need a migration).
EVENT_CREATED = "created"
EVENT_OUTCOME_CONFIRMED = "outcome_confirmed"
EVENT_OUTCOME_REVERTED = "outcome_reverted"
EVENT_QUARANTINED = "quarantined"
EVENT_ACTIVATED = "activated"

VALID_OUTCOME_KINDS = frozenset({"confirmed", "reverted"})


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _embedding_to_blob(vec: np.ndarray) -> bytes:
    arr = np.asarray(vec, dtype=np.float32)
    if arr.ndim != 1:
        raise ValueError(f"embedding must be 1-D, got shape {arr.shape}")
    return arr.tobytes()


def _blob_to_embedding(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


class ClassifierDB:
    """Persistence layer for classifier scenarios.

    All writes funnel through public methods so the audit log (SQL table +
    JSONL stream) stays consistent. No raw INSERT/UPDATE on the scenarios
    table from outside this module.
    """

    def __init__(
        self,
        db_path: "str | Path | None" = None,
        audit_log_path: "str | Path | None" = None,
    ):
        self._db_path = Path(db_path) if db_path is not None else Path(CLASSIFIER_DB_PATH)
        self._audit_log_path = (
            Path(audit_log_path) if audit_log_path is not None else Path(CLASSIFIER_AUDIT_LOG_PATH)
        )
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()
        self._run_migrations()
        self._seed_metadata()

    # ── Schema ───────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scenarios (
                scenario_id           INTEGER PRIMARY KEY AUTOINCREMENT,
                abstract_text         TEXT NOT NULL,
                abstract_text_v1      TEXT NOT NULL,
                abstract_rule_version INTEGER NOT NULL DEFAULT 1,
                intent_label          TEXT NOT NULL,
                intent_label_version  INTEGER NOT NULL DEFAULT 1,
                embedding             BLOB NOT NULL,
                embedding_model_id    TEXT NOT NULL DEFAULT 'multilingual-e5-large-instruct-v1',
                source_tag            TEXT NOT NULL,
                source_version        TEXT NOT NULL,
                source_ref            TEXT,
                outcome_confirmed     INTEGER NOT NULL DEFAULT 0,
                outcome_reverted      INTEGER NOT NULL DEFAULT 0,
                initial_confidence    REAL NOT NULL DEFAULT 0.5,
                extracted_value       TEXT,           -- Spec 2 v2: optional placeholder target ({P1}, etc.)
                active                INTEGER NOT NULL DEFAULT 1,
                schema_version        INTEGER NOT NULL DEFAULT 1,
                created_ts            TEXT NOT NULL,
                last_updated_ts       TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_scenarios_intent ON scenarios(intent_label, active);
            CREATE INDEX IF NOT EXISTS idx_scenarios_source ON scenarios(source_tag, source_version);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_scenarios_dedup
                ON scenarios(abstract_text, intent_label);

            CREATE TABLE IF NOT EXISTS schema_migrations (
                version       INTEGER PRIMARY KEY,
                description   TEXT NOT NULL,
                applied_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS label_evolution (
                old_label          TEXT NOT NULL,
                new_label          TEXT NOT NULL,
                effective_version  INTEGER NOT NULL,
                reason             TEXT,
                PRIMARY KEY (old_label, effective_version)
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                scenario_id     INTEGER NOT NULL,
                event_type      TEXT NOT NULL,
                delta           INTEGER,
                reason          TEXT,
                decision_id     TEXT,
                ts              TEXT NOT NULL,
                FOREIGN KEY (scenario_id) REFERENCES scenarios(scenario_id)
            );
            CREATE INDEX IF NOT EXISTS idx_audit_log_scenario ON audit_log(scenario_id);
            CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON audit_log(ts DESC);

            CREATE TABLE IF NOT EXISTS db_metadata (
                key    TEXT PRIMARY KEY,
                value  TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def _run_migrations(self) -> None:
        """Idempotent migration runner. Each version applied exactly once.

        Spec 1 ships at version 1 (the baseline). Future migrations append
        new (version, description, callable) entries to MIGRATIONS list.
        """
        applied = {row[0] for row in self._conn.execute("SELECT version FROM schema_migrations")}

        def _migration_v2_add_extracted_value(conn: sqlite3.Connection) -> None:
            """Spec 2 — add `extracted_value` column to scenarios. Carries
            the placeholder target (e.g. `{P1}`) so the graph classifier
            can de-abstract back to a real name at query time."""
            try:
                conn.execute("ALTER TABLE scenarios ADD COLUMN extracted_value TEXT")
            except sqlite3.OperationalError:
                # Column already present (CREATE TABLE statement was updated
                # before migration ran on a fresh DB) — no-op
                pass

        # version → (description, callable). Each callable receives self._conn.
        migrations: list[tuple[int, str, Any]] = [
            (1, "initial schema (Spec 1)", lambda _conn: None),
            (2, "Spec 2: extracted_value column", _migration_v2_add_extracted_value),
        ]
        for version, description, fn in migrations:
            if version in applied:
                continue
            fn(self._conn)
            self._conn.execute(
                "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)",
                (version, description, _now_iso()),
            )
        self._conn.commit()

    def _seed_metadata(self) -> None:
        """Insert default metadata rows on a fresh DB.

        INSERT OR IGNORE so a re-open is a no-op. created_at is captured
        only on the first open; subsequent opens see the original value.
        """
        defaults = [
            ("schema_version", str(SCHEMA_VERSION)),
            ("seed_version", str(SEED_VERSION)),
            ("embedding_model", CLASSIFIER_EMBEDDING_MODEL_ID),
            ("abstract_rule_version", str(CLASSIFIER_ABSTRACT_RULE_VERSION)),
            ("created_at", _now_iso()),
        ]
        for key, value in defaults:
            self._conn.execute(
                "INSERT OR IGNORE INTO db_metadata (key, value) VALUES (?, ?)",
                (key, value),
            )
        self._conn.commit()

    # ── Audit ────────────────────────────────────────────────────────────

    def _audit(
        self,
        scenario_id: int,
        event_type: str,
        *,
        delta: "int | None" = None,
        reason: "str | None" = None,
        decision_id: "str | None" = None,
    ) -> None:
        ts = _now_iso()
        self._conn.execute(
            "INSERT INTO audit_log (scenario_id, event_type, delta, reason, decision_id, ts) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (scenario_id, event_type, delta, reason, decision_id, ts),
        )
        # Mirror to JSONL append-only stream so per-deployment logs are
        # human-greppable without opening the SQLite file.
        try:
            with self._audit_log_path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {
                            "scenario_id": scenario_id,
                            "event_type": event_type,
                            "delta": delta,
                            "reason": reason,
                            "decision_id": decision_id,
                            "ts": ts,
                        }
                    )
                    + "\n"
                )
        except OSError as e:
            # Log path may be unwritable in tests / read-only envs. SQL row
            # is the source of truth; JSONL is best-effort.
            print(f"[ClassifierDB] audit log write failed: {e!r}")

    # ── Read API ─────────────────────────────────────────────────────────

    def query_nearest(
        self,
        embedding: np.ndarray,
        k: int = 20,
        active_only: bool = True,
    ) -> list[dict]:
        """k-NN over scenarios by cosine similarity.

        Embeddings are assumed to already be on a comparable scale
        (E5 returns L2-normalized vectors). Returns a list of dicts
        sorted by cosine DESC.
        """
        query = np.asarray(embedding, dtype=np.float32).reshape(-1)
        sql = "SELECT * FROM scenarios"
        if active_only:
            sql += " WHERE active = 1"
        rows = self._conn.execute(sql).fetchall()
        if not rows:
            return []

        # Stack embeddings for batch dot product. ~2k rows × 1024-dim is
        # ~8 MB — trivial; if this ever grows past 100k+, swap in FAISS.
        mat = np.stack([_blob_to_embedding(row["embedding"]) for row in rows])
        q_norm = float(np.linalg.norm(query))
        m_norms = np.linalg.norm(mat, axis=1)
        denom = q_norm * m_norms
        # Avoid zero-division for malformed zero vectors
        safe = np.where(denom > 0, denom, 1.0)
        sims = (mat @ query) / safe
        sims = np.where(denom > 0, sims, 0.0)

        # Top-k indices by descending similarity
        top_k = min(k, len(rows))
        order = np.argpartition(-sims, top_k - 1)[:top_k]
        order = order[np.argsort(-sims[order])]

        out: list[dict] = []
        for idx in order:
            row = rows[idx]
            out.append(self._row_to_dict(row, similarity=float(sims[idx])))
        return out

    def get_scenario(self, scenario_id: int) -> "dict | None":
        row = self._conn.execute(
            "SELECT * FROM scenarios WHERE scenario_id = ?",
            (scenario_id,),
        ).fetchone()
        return self._row_to_dict(row) if row is not None else None

    def get_metadata(self, key: str) -> "str | None":
        row = self._conn.execute(
            "SELECT value FROM db_metadata WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row is not None else None

    def count_scenarios(self, active_only: bool = True) -> int:
        sql = "SELECT COUNT(*) AS n FROM scenarios"
        if active_only:
            sql += " WHERE active = 1"
        return self._conn.execute(sql).fetchone()["n"]

    def resolve_label(self, label: str) -> str:
        """Apply label_evolution mapping. If `label` has been deprecated,
        return the most recent target; otherwise return as-is."""
        chain = self._conn.execute(
            "SELECT new_label FROM label_evolution WHERE old_label = ? "
            "ORDER BY effective_version DESC LIMIT 1",
            (label,),
        ).fetchone()
        return chain["new_label"] if chain is not None else label

    def _row_to_dict(self, row: sqlite3.Row, similarity: "float | None" = None) -> dict:
        d: dict[str, Any] = {key: row[key] for key in row.keys()}
        d["embedding"] = _blob_to_embedding(d["embedding"])
        d["intent_label"] = self.resolve_label(d["intent_label"])
        if similarity is not None:
            d["similarity"] = similarity
        return d

    # ── Write API ────────────────────────────────────────────────────────

    def insert_scenario(
        self,
        *,
        abstract_text: str,
        intent_label: str,
        embedding: np.ndarray,
        source_tag: str,
        source_version: str,
        source_ref: "str | None" = None,
        initial_confidence: float = 0.5,
        embedding_model_id: "str | None" = None,
        abstract_rule_version: "int | None" = None,
        intent_label_version: int = 1,
        outcome_confirmed: int = 0,
        outcome_reverted: int = 0,
        active: bool = True,
        skip_if_duplicate: bool = True,
        extracted_value: "str | None" = None,
    ) -> "int | None":
        """Insert a new scenario row. Returns the scenario_id, or None
        if `skip_if_duplicate=True` and (abstract_text, intent_label)
        already exists.
        """
        if not abstract_text or not abstract_text.strip():
            raise ValueError("abstract_text must be non-empty")
        if not intent_label or not intent_label.strip():
            raise ValueError("intent_label must be non-empty")

        ts = _now_iso()
        blob = _embedding_to_blob(embedding)
        emb_model = embedding_model_id or CLASSIFIER_EMBEDDING_MODEL_ID
        rule_v = abstract_rule_version or CLASSIFIER_ABSTRACT_RULE_VERSION

        sql_verb = "INSERT OR IGNORE" if skip_if_duplicate else "INSERT"
        cur = self._conn.execute(
            f"""
            {sql_verb} INTO scenarios (
                abstract_text, abstract_text_v1, abstract_rule_version,
                intent_label, intent_label_version,
                embedding, embedding_model_id,
                source_tag, source_version, source_ref,
                outcome_confirmed, outcome_reverted, initial_confidence,
                extracted_value,
                active, schema_version, created_ts, last_updated_ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                abstract_text, abstract_text, rule_v,
                intent_label, intent_label_version,
                blob, emb_model,
                source_tag, source_version, source_ref,
                int(outcome_confirmed), int(outcome_reverted), float(initial_confidence),
                extracted_value,
                1 if active else 0, SCHEMA_VERSION, ts, ts,
            ),
        )
        if cur.rowcount == 0:
            # INSERT OR IGNORE caught a duplicate
            self._conn.commit()
            return None
        scenario_id = cur.lastrowid
        self._conn.commit()
        self._audit(scenario_id, EVENT_CREATED, reason=f"source={source_tag}")
        return scenario_id

    def increment_outcome(
        self,
        scenario_id: int,
        kind: str,
        decision_id: "str | None" = None,
        reason: "str | None" = None,
    ) -> None:
        if kind not in VALID_OUTCOME_KINDS:
            raise ValueError(
                f"increment_outcome kind must be one of {sorted(VALID_OUTCOME_KINDS)}, got {kind!r}"
            )
        col = "outcome_confirmed" if kind == "confirmed" else "outcome_reverted"
        ts = _now_iso()
        cur = self._conn.execute(
            f"UPDATE scenarios SET {col} = {col} + 1, last_updated_ts = ? WHERE scenario_id = ?",
            (ts, scenario_id),
        )
        if cur.rowcount == 0:
            raise KeyError(f"scenario_id {scenario_id} not found")
        self._conn.commit()
        event = EVENT_OUTCOME_CONFIRMED if kind == "confirmed" else EVENT_OUTCOME_REVERTED
        self._audit(scenario_id, event, delta=1, reason=reason, decision_id=decision_id)

    def quarantine(self, scenario_id: int, reason: str) -> None:
        ts = _now_iso()
        cur = self._conn.execute(
            "UPDATE scenarios SET active = 0, last_updated_ts = ? WHERE scenario_id = ?",
            (ts, scenario_id),
        )
        if cur.rowcount == 0:
            raise KeyError(f"scenario_id {scenario_id} not found")
        self._conn.commit()
        self._audit(scenario_id, EVENT_QUARANTINED, reason=reason)

    def activate(self, scenario_id: int, reason: str) -> None:
        """Inverse of quarantine — restore a quarantined row."""
        ts = _now_iso()
        cur = self._conn.execute(
            "UPDATE scenarios SET active = 1, last_updated_ts = ? WHERE scenario_id = ?",
            (ts, scenario_id),
        )
        if cur.rowcount == 0:
            raise KeyError(f"scenario_id {scenario_id} not found")
        self._conn.commit()
        self._audit(scenario_id, EVENT_ACTIVATED, reason=reason)

    def add_label_evolution(
        self,
        old_label: str,
        new_label: str,
        effective_version: int,
        reason: "str | None" = None,
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO label_evolution "
            "(old_label, new_label, effective_version, reason) VALUES (?, ?, ?, ?)",
            (old_label, new_label, effective_version, reason),
        )
        self._conn.commit()

    # ── Bootstrap ────────────────────────────────────────────────────────

    def seed_from_jsonl(self, seed_path: "str | Path") -> int:
        """Load scenarios from a seed JSONL file. Each line:

            {
              "abstract_text": "...",
              "intent_label": "...",
              "embedding": [<base64-encoded float32 bytes>],
              "embedding_model_id": "...",
              "source_tag": "...",
              "source_version": "...",
              "source_ref": "...",
              "initial_confidence": 0.6
            }

        Embedding may be supplied as a list of floats or as base64-encoded
        bytes via "embedding_b64". Duplicates (same abstract_text + intent_label)
        are skipped silently. Returns count of newly-inserted rows.
        """
        import base64 as _b64

        path = Path(seed_path)
        if not path.exists():
            raise FileNotFoundError(f"seed file not found: {path}")

        inserted = 0
        with path.open("r", encoding="utf-8") as fh:
            for line_num, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"[ClassifierDB] seed line {line_num} invalid JSON: {e!r}")
                    continue

                # Embedding can come as list[float] or base64 bytes
                emb_field = rec.get("embedding")
                if isinstance(emb_field, str):
                    vec = np.frombuffer(_b64.b64decode(emb_field), dtype=np.float32)
                elif isinstance(emb_field, list):
                    vec = np.asarray(emb_field, dtype=np.float32)
                elif "embedding_b64" in rec:
                    vec = np.frombuffer(_b64.b64decode(rec["embedding_b64"]), dtype=np.float32)
                else:
                    print(f"[ClassifierDB] seed line {line_num} missing embedding")
                    continue

                sid = self.insert_scenario(
                    abstract_text=rec["abstract_text"],
                    intent_label=rec["intent_label"],
                    embedding=vec,
                    source_tag=rec.get("source_tag", "unknown"),
                    source_version=rec.get("source_version", "unknown"),
                    source_ref=rec.get("source_ref"),
                    initial_confidence=float(rec.get("initial_confidence", 0.5)),
                    embedding_model_id=rec.get("embedding_model_id"),
                    abstract_rule_version=rec.get("abstract_rule_version"),
                    extracted_value=rec.get("extracted_value"),
                    intent_label_version=int(rec.get("intent_label_version", 1)),
                    skip_if_duplicate=True,
                )
                if sid is not None:
                    inserted += 1
        return inserted

    # ── Snapshots ────────────────────────────────────────────────────────

    def snapshot(
        self,
        snapshot_dir: "str | Path | None" = None,
        retain_days: int = 30,
    ) -> str:
        """Copy the live DB to a date-stamped snapshot file. Prunes
        snapshots older than `retain_days` days. Returns the snapshot path.
        """
        snap_dir = Path(snapshot_dir) if snapshot_dir is not None else Path(CLASSIFIER_SNAPSHOT_DIR)
        snap_dir.mkdir(parents=True, exist_ok=True)
        # Best-effort flush WAL into main DB before copying
        try:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = snap_dir / f"classifier_scenarios_{stamp}.db"
        shutil.copy2(self._db_path, out)
        self._prune_snapshots(snap_dir, retain_days=retain_days)
        return str(out)

    def _prune_snapshots(self, snap_dir: Path, retain_days: int) -> int:
        cutoff = time.time() - retain_days * 86400
        removed = 0
        for p in snap_dir.glob("classifier_scenarios_*.db"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
                    removed += 1
            except OSError:
                pass
        return removed

    # ── Lifecycle ────────────────────────────────────────────────────────

    def checkpoint_wal(self) -> None:
        """Flush the WAL into the main DB file (TRUNCATE mode).

        Called at the end of each dream cycle so the -wal sidecar stays
        small and backup copies are self-contained."""
        try:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception as _e:
            print(f"[ClassifierDB] WAL checkpoint failed: {_e!r}")

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    def __enter__(self) -> "ClassifierDB":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
