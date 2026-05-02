"""Bootstrap orchestrator -- runs stages 1-6 sequentially.

Usage:
  python -m bootstrap.classifier.run_all

Each stage is a separate module so individual stages can be re-run on
their own. This script just chains them.

Cost: stages 1-2 free (download + filter); stage 3 ~$1.05 (Together.ai
70B); stages 4-6 free (NER + E5 + JSONL write).

Total wallclock: ~15-20 minutes assuming a warm cache.
"""
from __future__ import annotations

import sys
import time

STAGES = [
    ("stage_1_acquire",   "Download corpora (~10MB total)"),
    ("stage_2_filter",    "Filter to ~1700 utterances"),
    ("stage_3_classify",  "Classify with 70B (~$1.05)"),
    ("stage_4_abstract",  "spacy NER -> strip names + places"),
    ("stage_5_embed",     "Embed via E5"),
    ("stage_6_seed",      "Write data/classifier_scenarios_seed.jsonl"),
]


def main() -> int:
    overall_start = time.time()
    for name, description in STAGES:
        print(f"\n{'=' * 70}")
        print(f"STAGE: {name} -- {description}")
        print(f"{'=' * 70}")
        stage_start = time.time()
        try:
            module = __import__(f"bootstrap.classifier.{name}", fromlist=["main"])
            rc = module.main()
        except Exception as e:
            print(f"[run_all] {name} crashed: {e!r}")
            return 1
        elapsed = time.time() - stage_start
        if rc != 0:
            print(f"[run_all] {name} failed (rc={rc}) after {elapsed:.1f}s -- aborting")
            return rc
        print(f"[run_all] {name} ok ({elapsed:.1f}s)")

    total = time.time() - overall_start
    print(f"\n[run_all] all stages complete in {total / 60.0:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
