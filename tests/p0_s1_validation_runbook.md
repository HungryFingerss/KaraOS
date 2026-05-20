# P0.S1 — Anti-Spoof on Every Face Match — Live Canary Validation Runbook

**Date drafted:** 2026-05-18
**Author:** developer
**Status:** Ready for execution. All code/tests/docs/auditor-sign-off complete; live canary is the final closure gate per Plan v2 §9.

This runbook is the operational protocol for the live canary validation of P0.S1. The full code/test surface is documented in `tests/p0_s1_audit.md`, `tests/p0_s1_plan_v2.md`, `complete-plan.md::P0.S1`, and `everything_about_system.md §24.6`. This document is the **operator-facing checklist** for the three canary sessions plus the optional hardware-down dry-run.

---

## 1. Purpose

Verify end-to-end on a live system that the anti-spoof gate:

1. **Rejects** presentation attacks at the producer (background vision loop) — verdict propagates to TrackStore via atomic `upsert_embedding_with_verdict`.
2. **Blocks** the gallery write at the consumer (`progressive_enroll` site 5) — `add_embedding(... anti_spoof_verdict=False)` returns False, no gallery row appears.
3. **Preserves** D9 voice-only fallthrough — the visitor's session opens and voice profile seeds even when the face write is blocked.
4. **Surfaces** rejection signals to the dashboard via WatchdogAgent (`info` per-instance + `warning` burst alert at exact-equality threshold).
5. **Stays silent to the TTS channel** — never announces the defense (D10.c security UX).
6. **Passes** legitimate live engagement (negative control) — the gate does NOT false-reject a real face under each tested lighting condition.

All four phases of P0.S1 (Foundation / Producer / Consumer + watchdog / Invariants + tripwires) have structural+behavioral tests at 2266 passing. The canary is the empirical safety net that catches integration-level failures the test suite cannot.

---

## 2. Pre-flight — test environment setup

Before the first canary session, confirm:

| # | Item | Verification |
|---|---|---|
| 1 | Branch is at P0.S1 closure HEAD (no in-flight WIP). | `git status` clean. `git log -1` shows the P0.S1 closure commit. |
| 2 | Full test suite green. | `python -m pytest --tb=no -q` → `2302 passed, 4 skipped, 9 xfailed, 0 failed`. |
| 3 | Anti-spoof models present. | `ls models/antispoof_weights/*.pth` shows both `2.7_80x80_MiniFASNetV2.pth` + `4_0_0_80x80_MiniFASNetV1SE.pth`. |
| 4 | Camera responsive. | `python -c "import cv2; c=cv2.VideoCapture(0); ok,f=c.read(); print(ok, f.shape if ok else None)"` returns `True (H, W, 3)`. |
| 5 | brain.db + faces.db backups taken. | Copy `faces/brain.db` + `faces/faces.db` + `faces/faiss.index` to `faces/canary_backup_<date>/`. Restore-on-failure path is then trivial. |
| 6 | `terminal_output.md` archived. | Move to `terminal_output_pre_p0_s1_canary_<date>.md`. Fresh log per session is the evidence artifact. |
| 7 | Dashboard reachable. | `cd dog-ai-dashboard && npm run dev` → http://localhost:3000 loads + watchdog alerts feed is visible. |
| 8 | Owner enrolled. | One `person_type='best_friend'` row in `faces.db.persons`. (Jagan, in this deployment.) If absent, run `python pipeline.py` and complete first-boot enrollment before canary. |

If any pre-flight item fails, **stop and fix before scheduling sessions**.

---

## 3. Optional but recommended — hardware-down dry-run (~15 min)

Per the architect's recommendation, validate the `ANTI_SPOOF_REASON_UNAVAILABLE` path before stressing the `REJECTED` path. This is a 15-minute confidence check, not a closure-gate item, but it surfaces the fail-closed-on-unavailable behavior independently of attack-artifact effects.

**Steps:**

1. Stop pipeline.py if running.
2. `mv models/antispoof_weights models/antispoof_weights.tmp` — disables the MiniFASNet ensemble. `AntiSpoofChecker.__init__` will log `[Anti-spoof] DISABLED` and `checker.available` will be `False` on every call.
3. `python pipeline.py`. Wait for `[Pipeline] All systems ready. Watching...`.
4. Engage as the owner (Jagan, live face, real audio). Say "Hi Kara, can you hear me?"
5. Watch terminal_output.md AND dashboard. **Expected observations:**
   - `[Pipeline] Anti-spoof: BLOCKED progressive_enroll face write` (or similar — gate fires under `UNAVAILABLE` semantic).
   - Watchdog alert: `ANTI_SPOOF_REJECTION` with `metadata.reason='unavailable'` (NOT `'rejected'`).
   - Session opens, voice profile seeds (D9 fallthrough — engagement proceeds).
   - No TTS announcement of the gate (D10.c silent-to-speaker).
6. `Ctrl+C` shutdown.
7. `mv models/antispoof_weights.tmp models/antispoof_weights` — restore.
8. Restart pipeline.py and verify `checker.available=True` on first scan (look for `[Anti-spoof] summary over last N frames:` line at scan-100 mark; if it never appears, models didn't load).

**If unavailable-path verification fails:** stop and investigate before scheduling real canary. Most likely cause: rename target wrong, or PyTorch failed to import. Restore models, fix, retry.

---

## 4. The three independent canary sessions

Per Plan v2 §9, "independent" requires ALL FOUR of:

1. **Process restart** between sessions (no warm state, no in-memory caches).
2. **≥30 min wall-clock gap** between end-of-prior-session and start-of-next.
3. **Lighting condition variation** — no two sessions use the same lighting. Suggested matrix (pick any 3 distinct):
   - Daytime overhead (ceiling light + natural daylight)
   - Evening warm artificial (lamp at 2700K)
   - Morning natural through east-facing window
   - Dim ambient + single point-source lamp
   - Bright fluorescent (closest replication of office lighting)
4. **Attack-artifact regeneration** between sessions:
   - Photo: reprint OR use a different printed image. NOT the same physical print 3×.
   - Screen replay: re-capture on the attacker's phone OR use a different stored image.
   - Video replay: re-record OR use a different recorded clip.

Sessions can be same-day or spread across days. Spreading helps lighting variation; same-day is acceptable if the variation criterion is met another way (e.g. session 1 in living room, session 2 in bedroom, session 3 in office — three different ambient profiles).

### Per-session structure (~20-30 min per session)

Each session runs **3 attack types** + **1 negative control** + **1 burst reproduction** (only in session 1 — see §5.3).

The order within a session: negative control first → 3 attacks → optional burst. The negative-control-first ordering means a false-reject on the live face surfaces immediately (cancel session, investigate; do not proceed to attacks against a misbehaving gate).

---

## 5. The attack matrix

| Attack | Setup | Expected outcome | Verifies |
|---|---|---|---|
| **A. Printed photo** | High-quality print of Jagan's face on matte paper, held ~50cm from camera. Audio replay: phone speaker plays "Hi Kara, can you hear me?" near the print. | (1) Gate REJECTS via `verify_live` returning False. (2) Watchdog alert `ANTI_SPOOF_REJECTION` with `metadata.reason='rejected'`. (3) Progressive-enroll face write BLOCKED (no new row in `embeddings` for the visitor track). (4) Session opens via voice (D9 fallthrough). (5) No TTS announcement. | Producer-side detection of print attacks; consumer-side block; D9; D10.c. |
| **B. Phone screen replay** | Phone (held ~40cm from camera) displays a static photo of Jagan's face at full brightness. Audio replay: separate device plays the engagement phrase. | Same outcomes as A. The MiniFASNet ensemble's class-2 (replay) detector should fire higher than class-1 (live). | Screen-replay attack detection. Validates the V1SE backbone (4.0× scale crop captures screen reflectivity). |
| **C. Video recording** | Phone displays a short video of Jagan's face (head turning slightly, eyes blinking, ~10s loop). Held ~40cm from camera. Audio: same as B. | Same outcomes as A. Video adds motion vs. B's static image — verifies that motion alone does NOT defeat the gate. | Most adversarial of the three: motion + facial expression should still register as a screen-replay class. |
| **Negative control (live)** | Jagan in front of the camera, real face, real voice saying the engagement phrase. | (1) Gate PASSES (`verify_live` returns True). (2) Reason=`passed`. (3) Greeting proceeds normally. (4) `[Anti-spoof] summary` rolling log shows live_prob ≥ 0.9 typical. | Gate does NOT false-reject under the tested lighting. |
| **Burst (session 1 only)** | Three rapid attacks (any combination of A/B/C) within ~30 seconds against the same SORT track. | (1) Watchdog alert `ANTI_SPOOF_BURST` (severity=warning) fires EXACTLY ONCE at the 3rd rejection. (2) Subsequent 4th/5th rejections in the window do NOT re-fire the burst alert. (3) `count == ANTI_SPOOF_BURST_THRESHOLD` exact-equality verified. | §14b.1 exact-equality dispatch; C2 per-track burst aggregator. |

### 5.1 Attack execution checklist

Per attack, in order:

1. Start pipeline.py fresh. Confirm `[Pipeline] All systems ready. Watching...`.
2. Confirm the gate's pre-attack state on the dashboard: no recent `ANTI_SPOOF_REJECTION` alerts within the last 5 min.
3. Present the attack artifact. Hold steady for ~5 seconds (give scan loop ≥3 detections).
4. Trigger the engagement phrase via audio replay.
5. Watch terminal_output.md AND dashboard within the next 10 seconds.
6. Record the result in the evidence-logging template (§7).
7. If the attack is rejected as expected, wait ≥10s before next attack (avoid burst alert on attacks A and B during single-attack measurement; only session 1's burst-reproduction attempt deliberately stacks 3 within window).
8. If the attack is NOT rejected (gate let it through), **stop immediately**. Investigate before continuing. Possible causes:
   - Anti-spoof checker silently fell back to unavailable mode (check `checker.available`).
   - Threshold tuning regression (`ANTISPOOFING_THRESHOLD` should be 0.5).
   - Camera focus / lighting genuinely defeated MiniFASNet (rare with 0.5 threshold; investigate per-frame `[Anti-spoof]` log lines).

### 5.2 Negative-control execution

Negative control runs FIRST in each session. If the live face is false-rejected:

1. Note the lighting condition, camera angle, and any other environmental factors.
2. Check `LOG_ANTISPOOF_SUMMARY` rolling line for the live_prob distribution.
3. **Cancel the session** — do not proceed to attacks. False-reject on live face indicates either a real gate calibration issue OR an environmental factor that needs documenting.
4. Investigate, fix or document, then restart the session from scratch.

### 5.3 Burst reproduction — session 1 only

After the 3 attacks + negative control complete cleanly in session 1, perform the burst reproduction:

1. Without restarting pipeline.py (the rejection store still holds the 3 attack timestamps from this session — but only if all 3 attacks targeted the SAME SORT track; in practice, restarting between attacks means each was a fresh track).
2. Better: deliberately stack the burst. Start pipeline.py fresh, then within ~45 seconds (under the 60-second window), present 3 attack artifacts back-to-back against what should be the same track (keep the artifacts in the same field of view continuously between presentations).
3. Watch for `[WatchdogAgent] ANTI_SPOOF_BURST (warning): track=<id> count=3/3 in 60s` log line + dashboard alert.
4. Continue with a 4th attack within the window. **Burst alert must NOT re-fire** (exact-equality, not `>=`).
5. Wait ≥61 seconds. Trigger a 5th attack. The rejection store has now pruned the original 3 timestamps; this attack should record as the new first-in-window (count=1, no burst).

Sessions 2 and 3 do NOT require burst reproduction — one verified instance per closure is sufficient.

---

## 6. Closure gate

P0.S1 is considered fully closed when:

- [ ] **9 successful rejections** — 3 attack types × 3 sessions, each correctly rejected with the expected reason code and dashboard alert.
- [ ] **3 successful negative-control passes** — 1 per session, live face engages normally under each tested lighting condition.
- [ ] **1 successful burst reproduction** — burst alert fires exactly once at the 3rd rejection in a single session.
- [ ] **Zero unexpected behaviors** — no TTS announcements of the gate, no false-rejects on live faces, no missed burst alerts, no gallery rows for blocked attempts.

Anything less = closure blocked; investigate before retrying.

Partial-success protocol: if 7-8 of 9 rejections succeed but 1-2 fail, **do not declare closure**. Identify the failure mode (lighting? attack-artifact quality? unexpected MiniFASNet behavior on the specific input?), document, and either fix-then-retry or surface the gap as a P0.S1.Y follow-up for the architect's adjudication.

---

## 7. Evidence-logging template

For each session, fill in this template and commit as `tests/p0_s1_canary_logs/session_<N>_<date>.md`. The committed log is the closure evidence.

```markdown
# P0.S1 Canary — Session <N> — <YYYY-MM-DD HH:MM>

## Environment
- Lighting: <description>
- Camera distance: <cm>
- Operator: <name>
- Pipeline commit SHA: <git rev-parse HEAD>

## Pre-flight
- [ ] Items 1-8 from §2 verified
- [ ] Hardware-down dry-run passed (if first session)

## Negative control (live face)
- Result: PASS / FAIL
- Reason code: passed
- Notes: <e.g. "live_prob distribution 0.94-0.99 across 5 detections">

## Attack A — Printed photo
- Print source: <fresh print | reused>
- Result: REJECTED / FALSE-ACCEPT
- Reason code: rejected
- Dashboard alert observed at: <HH:MM:SS>
- Gallery row count for visitor track post-attack: 0 (expected) | <N> (FAIL)
- Notes: <any non-default observations>

## Attack B — Phone screen replay
- Phone model: <name>
- Result: REJECTED / FALSE-ACCEPT
- Reason code: rejected
- Dashboard alert observed at: <HH:MM:SS>
- Gallery row count for visitor track post-attack: 0
- Notes: <any non-default observations>

## Attack C — Video recording
- Video source: <fresh recording | reused>
- Result: REJECTED / FALSE-ACCEPT
- Reason code: rejected
- Dashboard alert observed at: <HH:MM:SS>
- Gallery row count for visitor track post-attack: 0
- Notes: <any non-default observations>

## Burst reproduction (session 1 only)
- Stack window observed: <secs>
- First burst alert at attack #: <3, expected>
- Subsequent 4th/5th attacks re-fired burst: NO (expected) | YES (FAIL)
- Notes: <any non-default observations>

## Terminal log excerpt
<paste relevant [Pipeline] / [Anti-spoof] / [WatchdogAgent] lines>

## Outcome
- Session passes / fails closure-gate criteria.
- Carry-forward to next session: <any environmental adjustments needed>
```

---

## 8. Reference docs

- `tests/p0_s1_audit.md` — Phase 0 audit (D1-D8 + threat model + 5 call-site enumeration).
- `tests/p0_s1_plan_v1.md` — Plan v1 (locked D1-D10 + C0-C3).
- `tests/p0_s1_plan_v2.md` — Plan v2 (auditor's 9 precision items + §14b clarifications; §9 has the live-canary criteria this runbook operationalizes).
- `complete-plan.md::P0.S1` — closure summary including discipline-count bumps + bookmarks.
- `everything_about_system.md §24.6` — narrative + load-bearing properties + AntiSpoofRejectionStore rationale.
- `tests/test_p0_s1_phase1.py` / `tests/test_p0_s1_phase2.py` / `tests/test_p0_s1_phase3.py` / `tests/test_p0_s1_phase4.py` — 50 tests across the four phases (canary supplements; does not replace).
