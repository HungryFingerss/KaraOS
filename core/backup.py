"""
Daily SQLite online-backup of faces.db and brain.db.

Uses sqlite3.Connection.backup() — safe under concurrent WAL writes (raw file copy is unsafe for WAL-mode DBs).
The online backup API page-iterates with low pressure on writers; never use raw file copy
for a WAL-mode DB because a mid-checkpoint copy produces silent corruption.
"""
import re
import sqlite3
import logging
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

SNAPSHOT_DIR_DEFAULT = "faces/snapshots"
SNAPSHOT_RETENTION_DAYS = 30

_DATED_FILENAME_RE = re.compile(r'.*_(\d{4}-\d{2}-\d{2})\.db$')
_LAST_BACKUP_FILENAME = ".last_backup"


def daily_snapshot(
    db_path: str,
    *,
    snapshot_dir: str = SNAPSHOT_DIR_DEFAULT,
    today: date | None = None,
) -> tuple[bool, str]:
    """
    Take a SQLite online-backup of db_path into snapshot_dir.

    Filename: {basename_with_underscores}_{YYYY-MM-DD}.db
    e.g. faces_db_2026-05-06.db

    Returns (created: bool, path: str).
    created=False if today's snapshot already exists (idempotent — earlier-in-day snapshot wins).
    Never raises — logs errors and returns (False, "").
    """
    if today is None:
        today = date.today()

    try:
        snap_dir = Path(snapshot_dir)
        snap_dir.mkdir(parents=True, exist_ok=True)

        src = Path(db_path)
        # Convert dots to underscores for clean filename: faces.db → faces_db
        base = src.name.replace(".", "_")
        dated_name = f"{base}_{today.isoformat()}.db"
        dest = snap_dir / dated_name

        if dest.exists():
            return False, str(dest)

        src_conn = sqlite3.connect(str(src))
        try:
            dest_conn = sqlite3.connect(str(dest))
            try:
                src_conn.backup(dest_conn)
            finally:
                dest_conn.close()
        finally:
            src_conn.close()

        return True, str(dest)

    except Exception as e:
        logger.error(f"[Backup] daily_snapshot failed for {db_path}: {e!r}")
        return False, ""


def prune_old_snapshots(
    snapshot_dir: str = SNAPSHOT_DIR_DEFAULT,
    *,
    retention_days: int = SNAPSHOT_RETENTION_DAYS,
    now: datetime | None = None,
) -> list[str]:
    """
    Delete snapshot files older than retention_days.

    Only files matching the dated filename pattern are eligible —
    unrelated files in the directory are never touched.

    Returns list of deleted paths.
    """
    if now is None:
        now = datetime.now()

    deleted: list[str] = []
    snap_dir = Path(snapshot_dir)

    if not snap_dir.exists():
        return deleted

    try:
        for f in snap_dir.iterdir():
            if not f.is_file():
                continue
            m = _DATED_FILENAME_RE.match(f.name)
            if not m:
                continue
            try:
                file_date = datetime.strptime(m.group(1), "%Y-%m-%d")
                age_days = (now - file_date).days
                if age_days > retention_days:
                    f.unlink()
                    deleted.append(str(f))
            except Exception as e:
                logger.warning(f"[Backup] prune_old_snapshots skipped {f}: {e!r}")
    except Exception as e:
        logger.error(f"[Backup] prune_old_snapshots failed: {e!r}")

    return deleted


def run_daily_backup_pass(
    db_paths: list[str] | None = None,
    *,
    snapshot_dir: str = SNAPSHOT_DIR_DEFAULT,
    retention_days: int = SNAPSHOT_RETENTION_DAYS,
) -> dict:
    """
    Convenience driver: snapshot all db_paths (default: faces.db + brain.db) then prune old.

    Returns:
        {
            'snapshots_created': [...],
            'snapshots_skipped': [...],
            'pruned': [...],
            'errors': [...],
        }

    Never raises — collects errors and returns them.
    """
    if db_paths is None:
        from core.config import DB_PATH, BRAIN_DB_PATH
        db_paths = [str(DB_PATH), str(BRAIN_DB_PATH)]

    result: dict = {
        "snapshots_created": [],
        "snapshots_skipped": [],
        "pruned": [],
        "errors": [],
    }

    for path in db_paths:
        try:
            created, dest = daily_snapshot(path, snapshot_dir=snapshot_dir)
            if created:
                result["snapshots_created"].append(dest)
            elif dest:
                result["snapshots_skipped"].append(dest)
            else:
                result["errors"].append(f"snapshot failed for {path}")
        except Exception as e:
            result["errors"].append(f"{path}: {e!r}")

    try:
        pruned = prune_old_snapshots(snapshot_dir, retention_days=retention_days)
        result["pruned"].extend(pruned)
    except Exception as e:
        result["errors"].append(f"prune failed: {e!r}")

    return result
