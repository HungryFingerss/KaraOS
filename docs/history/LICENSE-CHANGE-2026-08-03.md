# License change — Apache-2.0 → proprietary source-available (2026-08-03)

**What changed.** The first-party license moved from Apache License 2.0 to
the KaraOS Source-Available License (Evaluation Only), SPDX reference
`LicenseRef-KaraOS-Proprietary`. Files touched: `LICENSE` (replaced),
`NOTICE` (proprietary framing added; the three vendored attributions kept
verbatim), 367 in-place SPDX header swaps at identical line counts,
`README.md` and `CONTRIBUTING.md` license sections, and the licensing CI
re-pins in `tests/test_pre_p1_bundle2_docs_governance.py` (A1/A7). One
latent gap fixed in passing: `.github/workflows/pages.yml` carried no SPDX
header at all (it predates this change; the A6 invariant had been failing
on it — the idempotency test's script run healed it during verification).

**Why.** Owner decision (Jagan, 2026-08-03): KaraOS is the product and the
moat; the public repo exists for evaluation — including the YC application
review window, during which the repo link must remain live — not for reuse.
Visibility and grant are separate levers: this change removes the grant
while keeping the repo readable. The plan of record is to make the repo
private after the YC window (on or after 2026-08-29), at which point a
docs-only public showcase repo can carry the blueprint if wanted.

**Evidence.** Full suite green in the exact tree pushed (run recorded in
the commit message); the 367-file header parametrize, the script
idempotency test, and the re-pinned governance tests all pass. The header
swap preserved line counts per file, so no line-anchored invariant
drifted.

**What was decided against.** (a) Making the repo private immediately —
rejected because the YC application links to it and a 404 mid-review reads
as a dead project. (b) Hiding the Apache history — rejected; LICENSE §4
states plainly that pre-2026-08-03 snapshots remain Apache-2.0 for their
recipients, because prior open-source grants are irrevocable for copies
already distributed and pretending otherwise would be false. Exposure at
change time: 0 forks, 1 star, 0 watchers.

**Known limitations.** (1) The in-flight `sb2-llm-local-flip` branch still
carries Apache-2.0 headers in its tree; at merge time the re-pinned CI
will fail any branch-added files until their headers are swapped — that is
the gate working, and the merge commit should run
`python tools/add_spdx_headers.py` to close the stragglers. (2) This
license text has not yet had legal review; counsel should read it before
YC paperwork. (3) The claude.ai artifact copy of the blueprint predates
the one-line role-text update in this commit; it syncs at the next
artifact republish.
