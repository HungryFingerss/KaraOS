"""Stage 1 -- Acquire bootstrap dialogue corpora.

Downloads three license-clean dialogue corpora to bootstrap/classifier/cache/.
Idempotent: re-runs skip already-downloaded archives.

Sources:
  - Cornell Movie-Dialogs Corpus (~10MB, free academic)
  - DailyDialog (~4MB, free academic)
  - EmpatheticDialogues (~30MB, CC-BY 4.0)

Friends + AMI deliberately excluded (held out as test sets -- including
them as bootstrap data would be data leakage).

Run: python -m bootstrap.classifier.stage_1_acquire
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import hashlib
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


CORPORA = [
    {
        "name":     "cornell",
        "url":      "https://www.cs.cornell.edu/~cristian/data/cornell_movie_dialogs_corpus.zip",
        "archive":  "cornell_movie_dialogs_corpus.zip",
        "out_dir":  "cornell",
        "size_mb":  "~10",
    },
    {
        "name":     "dailydialog",
        "url":      "http://yanran.li/files/ijcnlp_dailydialog.zip",
        "archive":  "ijcnlp_dailydialog.zip",
        "out_dir":  "dailydialog",
        "size_mb":  "~4",
    },
    {
        "name":     "empathetic",
        "url":      "https://dl.fbaipublicfiles.com/parlai/empatheticdialogues/empatheticdialogues.tar.gz",
        "archive":  "empatheticdialogues.tar.gz",
        "out_dir":  "empathetic",
        "size_mb":  "~30",
    },
]


def _download(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  [skip] {dest.name} already cached ({dest.stat().st_size // 1024} KB)")
        return
    print(f"  [download] {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=120) as resp, tmp.open("wb") as out:
            shutil.copyfileobj(resp, out)
    except Exception as e:
        print(f"  [error] {e!r}")
        if tmp.exists():
            tmp.unlink()
        raise
    tmp.replace(dest)
    sha = hashlib.sha256(dest.read_bytes()).hexdigest()[:16]
    print(f"  [ok] {dest.name} ({dest.stat().st_size // 1024} KB) sha256:{sha}")


def _extract(archive: Path, out_dir: Path) -> None:
    if out_dir.exists() and any(out_dir.iterdir()):
        print(f"  [skip] {out_dir.name}/ already extracted")
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"  [extract] {archive.name} -> {out_dir.name}/")
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(out_dir)
    elif archive.suffixes[-2:] == [".tar", ".gz"] or archive.name.endswith(".tar.gz"):
        import tarfile
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(out_dir)
    else:
        raise ValueError(f"unknown archive type: {archive}")


def main() -> int:
    print(f"Cache dir: {CACHE_DIR}")
    for spec in CORPORA:
        print(f"\n[{spec['name']}] ({spec['size_mb']} MB)")
        archive = CACHE_DIR / spec["archive"]
        try:
            _download(spec["url"], archive)
            _extract(archive, CACHE_DIR / spec["out_dir"])
        except Exception as e:
            print(f"[stage_1_acquire] {spec['name']} failed: {e!r}")
            print(f"  (proceeding to next corpus -- partial bootstrap is OK)")
    print("\n[stage_1_acquire] done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
