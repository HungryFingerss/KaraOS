"""
Disk space monitoring with idempotent threshold alerts.
Wave 5 / Item 20 — production observability for unbounded data growth.

Single-volume assumption: shutil.disk_usage monitors the volume that contains
root_path. If KaraOS ever runs with faces/ and data/ on separate volumes, only
the root volume's usage is tracked here.
"""
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Module state for alert idempotency. Resets on process restart — a restart with
# disk already over threshold re-fires the alert on the first health cycle (correct:
# operator wants to know at boot if the disk is already full).
_last_disk_alert_level: int = 0


@dataclass
class DiskSnapshot:
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent_used: float
    per_directory_bytes: "dict[str, int]"  # {"faces/": 124_000_000, ...}


def gather_disk_snapshot(
    *,
    root_path: str = ".",
    monitored_dirs: "list[str] | None" = None,
) -> DiskSnapshot:
    """Single-volume disk usage + per-directory size breakdown.

    monitored_dirs defaults to KaraOS's standard data dirs.
    Missing directories are reported as 0 bytes (no error).
    """
    if monitored_dirs is None:
        from core.config import DISK_MONITORED_DIRS
        monitored_dirs = DISK_MONITORED_DIRS

    usage = shutil.disk_usage(root_path)

    per_dir: dict[str, int] = {}
    for d in monitored_dirs:
        per_dir[d] = _dir_size(d)

    return DiskSnapshot(
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
        percent_used=(usage.used / usage.total) * 100.0,
        per_directory_bytes=per_dir,
    )


def _dir_size(path: str) -> int:
    """Recursive directory size in bytes. Missing dir → 0 without raising."""
    p = Path(path)
    if not p.exists():
        return 0
    total = 0
    try:
        for f in p.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass  # file vanished mid-walk
    except Exception as e:
        logger.warning(f"[Disk] _dir_size({path}) failed: {e!r}")
    return total


def format_disk_line(s: DiskSnapshot) -> str:
    used_gb  = s.used_bytes  / 1_000_000_000
    total_gb = s.total_bytes / 1_000_000_000

    parts = [f"used={used_gb:.1f}GB/{total_gb:.0f}GB ({s.percent_used:.1f}%)"]
    for d, b in s.per_directory_bytes.items():
        if b == 0:
            continue
        parts.append(f"{d.rstrip('/')}={_human_bytes(b)}")

    return "[Disk] " + " | ".join(parts)


def _human_bytes(n: int) -> str:
    if n < 1_000_000:
        return f"{n / 1_000:.0f}KB"
    if n < 1_000_000_000:
        return f"{n / 1_000_000:.0f}MB"
    return f"{n / 1_000_000_000:.1f}GB"


def check_disk_thresholds(
    snapshot: DiskSnapshot,
    brain_orchestrator: Any,
) -> "str | None":
    """Fire watchdog alerts on threshold crossings.

    Idempotent: only fires when crossing UP from a lower level.
    Usage dropping below a threshold resets the level so future crossings re-alert.
    Returns the alert_type string fired, or None if nothing to do.
    """
    global _last_disk_alert_level
    from core.config import DISK_ALERT_WARNING_PCT, DISK_ALERT_CRITICAL_PCT, DISK_ALERT_BLOCKER_PCT

    pct = snapshot.percent_used
    new_level = 0
    if pct >= DISK_ALERT_BLOCKER_PCT:
        new_level = DISK_ALERT_BLOCKER_PCT
    elif pct >= DISK_ALERT_CRITICAL_PCT:
        new_level = DISK_ALERT_CRITICAL_PCT
    elif pct >= DISK_ALERT_WARNING_PCT:
        new_level = DISK_ALERT_WARNING_PCT

    if new_level > _last_disk_alert_level:
        try:
            severity = "critical" if new_level >= DISK_ALERT_CRITICAL_PCT else "warning"
            alert_type = (
                f"disk_critical_{new_level}"
                if new_level >= DISK_ALERT_BLOCKER_PCT
                else f"disk_warning_{new_level}"
            )
            brain_orchestrator.watchdog.report_disk_threshold(
                level=new_level,
                percent_used=pct,
                free_bytes=snapshot.free_bytes,
                severity=severity,
            )
            print(
                f"[Disk-Alert] threshold {new_level}% crossed — {pct:.1f}% used, "
                f"{_human_bytes(snapshot.free_bytes)} free"
            )
            _last_disk_alert_level = new_level
            return alert_type
        except Exception as e:
            logger.error(f"[Disk] alert fire failed: {e!r}")
    elif new_level < _last_disk_alert_level:
        # Usage dropped below the last alerted level — reset so future crossings re-alert
        _last_disk_alert_level = new_level

    return None


def reset_alert_level() -> None:
    """Test helper. Resets module-level alert state."""
    global _last_disk_alert_level
    _last_disk_alert_level = 0
