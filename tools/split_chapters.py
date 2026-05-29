"""One-shot mechanical extraction: split everything_about_system.md into 19 chapter files.

Per Plan v2 §1.4 cluster table + §1.6 section-number stability invariant.

Line boundaries derived from fresh H2 grep at Phase 4 execution time (2026-05-28):
    Grep `^## ` returns 343 H2 headings; §1 at line 493, §340 at line 9186, EOF at 9214.

Mechanical extraction: verbatim source line ranges, zero content edits inside section bodies.
Each chapter file gets a one-line preamble identifying the source range; the rest is verbatim.

Re-runnable: deletes target chapter files before writing if --force is supplied (default-deny).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import argparse
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "everything_about_system.md"
OUT_DIR = REPO_ROOT / "docs" / "architecture"

# Plan v2 §1.4 cluster table — verified against fresh H2 grep 2026-05-28.
# Plan v2 §1.4 reported CH07 ending at line 3437; actual is 3302 (§72 starts at 3303).
# Treated as Plan-v2-line-range-drift, banked at closure narrative.
CHAPTERS = [
    (1,  493,  1115, "introduction_and_tech_stack",                       "Introduction + Tech Stack",                            "1-9"),
    (2,  1116, 1393, "lifecycle_and_pipeline_states",                     "Lifecycle + Pipeline States",                          "10-15"),
    (3,  1394, 1935, "async_and_vision_basics",                           "Async + Vision Basics",                                "16-29"),
    (4,  1936, 2102, "audio_and_stt_tts",                                 "Audio + STT/TTS",                                      "30-35"),
    (5,  2103, 2423, "face_voice_galleries",                              "Face/Voice Galleries",                                 "36-46"),
    (6,  2424, 2924, "sessions_and_evidence",                             "Sessions + Evidence",                                  "47-58"),
    (7,  2925, 3302, "reconciler_and_conversation_turn",                  "Reconciler + Conversation Turn",                       "59-71"),
    (8,  3303, 4359, "prompt_blocks_and_brain_agents",                    "Prompt Blocks + Brain Agents",                         "72-99"),
    (9,  4360, 4634, "dispute_tool_privileges_logging",                   "Dispute + Tool Privileges + Logging",                  "100-118"),
    (10, 4635, 5163, "schemas_tests_dashboard",                           "Schemas + Tests + Dashboard",                          "119-140b"),
    (11, 5164, 5704, "future_work_reference_tables",                      "Future Work + Reference Tables",                       "141-149"),
    (12, 5705, 6540, "privacy_rooms_recent_work",                         "Privacy + Rooms + Recent Work",                        "150-176"),
    (13, 6541, 6822, "observability_evolution_plans_pyannote",            "Observability 2.0 + Evolution Plans + Pyannote",       "177-197"),
    (14, 6823, 7259, "voice_vision_independence_pure_graph_classifier",   "Voice/Vision Independence + Pure-Graph Classifier",    "198-214"),
    (15, 7260, 7709, "external_benchmarks_multilayer_architecture",       "External Benchmarks + Multi-Layer Architecture",       "215-232"),
    (16, 7710, 8215, "p0_correctness_store_session_migrations",           "P0 Correctness Foundations + Store/Session Migrations","233-270"),
    (17, 8216, 8611, "p0_timeout_schema_router_concurrency_property",     "P0 Timeout + Schema + Router/Concurrency/Property",    "271-299"),
    (18, 8612, 8934, "observability_ci_event_log",                        "Observability + Tiered CI + Event Log Foundation",     "300-321"),
    (19, 8935, 9214, "architectural_disciplines_upcoming_work",           "Architectural Disciplines + Upcoming Work",            "322-340"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Overwrite existing chapter files")
    args = parser.parse_args()

    if not SOURCE.exists():
        print(f"ERROR: source not found at {SOURCE}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    text = SOURCE.read_text(encoding="utf-8")
    lines = text.split("\n")
    print(f"Source lines: {len(lines)}")
    print(f"Source bytes: {len(text.encode('utf-8'))}")

    total_body = 0
    for n, start, end, slug, topic, sections in CHAPTERS:
        cn = f"{n:02d}"
        fname = f"CHAPTER_{cn}_{slug}.md"
        out_path = OUT_DIR / fname
        if out_path.exists() and not args.force:
            print(f"SKIP CH{cn}: file exists (use --force to overwrite)")
            continue
        body_lines = lines[start - 1:end]
        preamble = (
            f"> **CHAPTER {cn} \u2014 {topic}** | "
            f"Sourced from `everything_about_system.md` \u00a7{sections} "
            f"(verbatim mechanical extraction per Plan v2 \u00a71.6 section-number stability invariant).\n"
            f"\n---\n"
        )
        body = "\n".join(body_lines)
        content = preamble + "\n" + body + "\n"
        out_path.write_text(content, encoding="utf-8", newline="\n")
        total_body += len(body_lines)
        print(f"CH{cn}: {len(body_lines):>5} lines [\u00a7{sections:>8}] -> {fname}")

    expected = 9214 - 493 + 1
    print()
    print(f"Total chapter body lines written: {total_body}")
    print(f"Expected (lines 493-9214 inclusive): {expected}")
    if total_body != expected:
        print(f"WARNING: drift {total_body - expected} lines")
        return 2
    print("OK: body line count matches source range exactly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
