# KaraOS

![fast CI](https://github.com/HungryFingerss/KaraOS/actions/workflows/fast.yml/badge.svg)
![nightly CI](https://github.com/HungryFingerss/KaraOS/actions/workflows/slow.yml/badge.svg)
![security scan](https://github.com/HungryFingerss/KaraOS/actions/workflows/security.yml/badge.svg)

KaraOS is a domain-agnostic embodied-presence runtime, the cognitive layer for
an embodied AI agent: it sees, hears, recognizes people, remembers them across
sessions, and holds spoken conversations. What it deploys AS is selected by a
profile + persona pack (`profiles/` + `persona/`); the companion, this repo's
default profile, is the first reference persona:
see a face, identify, greet, listen, respond, repeat.

## What's actually in this repo

The whole thing lives here: the runtime, its 4,200+ test suite, the CI/CD, the
evaluation benches, the published benchmark results, and the engineering rule
book. Every folder has its own README describing exactly what's inside.

```
karaos/
├── core/ # the engine: perception, identity, memory, speech, resilience
├── runtime/ # the engine/app seam (extracted from the old pipeline monolith)
├── flows/ # the app layer: use-case choreography (companion today)
├── pipeline.py # the main async loop (entry point: python pipeline.py)
├── profiles/ # deployment config as data (companion.yaml, robotics.yaml)
├── persona/ # persona packs: who the deployment IS (data-only YAML)
├── models/ # bundled ONNX/pth weights via Git LFS (~600MB)
├── tests/ # 189 test files — behavioral goldens + ~25 AST invariants
├── bench/ # perception eval harness (face EER + attribution, CI-gated)
├── karaos-dashboard/ # Next.js local dashboard (token-auth, localhost-bound)
├── deploy/ # systemd + supervisord units + operator runbook
├── tools/ # operator CLIs (factory reset, event-log replay, SPDX)
├── bootstrap/ # one-shot offline pipelines (built the classifier seed)
├── data/ # the classifier seed (system intelligence; survives reset)
├── docs/ # 19-chapter architecture reference + policies
├── published-papers-tests/ # external benchmark validation (the honest journey)
├── terminal-logs/ # raw live-session demo logs
├── rule book/ # the engineering disciplines + the 170-spec cycle archive
├── enroll.py # standalone enrollment CLI
├── delete_person.py / audit_person.py / repair_gallery.py # person-lifecycle CLIs
├── sim_runner.py # headless conversation simulator (turns_*.txt scripts)
└── faces/ # runtime data: face DB, memories (auto-created, gitignored)
```

## Setup

**The complete, follow-as-is manual is [SETUP.md](SETUP.md)**, every step with
what you'll see, the gotchas, and troubleshooting. It was verified end-to-end
on a fresh clone (2026-07-03): running it exactly produced a working system
and a green test suite (4,233 passed / 0 failed, CPU-only machine).

The short version:

```bash
git clone https://github.com/HungryFingerss/KaraOS.git karaos && cd karaos
git lfs pull # model weights (~600 MB)
python -m venv venv && venv\Scripts\activate # Linux: source venv/bin/activate
python -m pip install --upgrade pip "setuptools<81" wheel # REQUIRED before the next line
pip install -r requirements.txt # ~5-15 min, 0 errors expected
copy .env.example .env # then set TOGETHER_API_KEY in .env
python pipeline.py # first boot enrolls YOU (voice + face)
```

Dashboard (optional): `cd karaos-dashboard && npm install && npm run dev`.
The pipeline terminal prints the one-time auth URL, then http://localhost:3000.

### Pre-commit hook (P0.S6 secrets-scanning)

Install once per dev machine so staged commits get scanned for accidentally-leaked
secrets via [detect-secrets](https://github.com/Yelp/detect-secrets):

```bash
pip install pre-commit detect-secrets
pre-commit install
```

The `.secrets.baseline` file is the allowlist snapshot of known false positives
(ML embeddings, git SHAs, etc.). New high-entropy findings outside the baseline
fail the commit. To refresh the baseline after legitimately adding a new
high-entropy file: `detect-secrets scan --baseline .secrets.baseline --update`.

## Tests: the proof the thing works

**4,237 passing / 0 failed** (4,259 collected). Behavioral golden tests drive the
real pipeline with only hardware mocked; ~25 structural-invariant files enforce
the engineering rules by AST scan (no silent excepts, no wall-clock deadline
math, layering boundaries, secrets hygiene, paired-write atomicity, the rule
book made executable).

```bash
python -m pytest --ignore=tests/test_brain_json_parser_hypothesis.py -q
```

See `tests/README.md` for the layers, markers, and conventions.

## CI/CD: what runs automatically

| Workflow | Trigger | What it does |
|---|---|---|
| `fast.yml` | every push + PR | ruff + mypy (informational) + the fast test subset (`-m "not slow and not network and not models"`), plus the privacy-critical tests as a separate fail-on-skip step |
| `slow.yml` | nightly + manual | the FULL suite with model caches + the perception bench (`bench/perception --alert`) in a companion + robotics profile matrix, LFS enabled |
| `security.yml` | weekly + on requirements change | pip-audit + Trivy filesystem scan (SARIF to the Security tab) |
| `trufflehog.yml` | PR diff + weekly | secret scanning (diff on PRs, full-history on schedule) |

## Benchmarks & evidence

- `bench/perception/`: the CI-gated perception numbers (face EER 0.0625 on the
  synthetic gate, attribution 51/51 golden routing cases) with committed,
  human-reviewed baselines.
- `published-papers-tests/`: validation against a published academic benchmark,
  including the honest journey (the run that looked great, the falsifying
  experiment that cut it down, and the rewrite that earned the number back).
- `terminal-logs/`: raw, unedited live-session logs from real demos.

## Enrollment

**Voice:** Say "add me", "enroll me", "remember me" to the system.
It asks your name then captures your face for 5 seconds.

**Manual:** Go to http://localhost:3000/enroll, enter name, click start.

**Script:** `python enroll.py --name "Your Name"`

## The rule book

`rule book/` holds the engineering operating system this repo was built under: the per-role disciplines (architect / developer / auditor), each rule with its
provenance and its CI-enforcement pointer, plus the 170-file cycle-spec archive
the rules were earned from.

## Hardware targets

- **Now:** Windows laptop (development + testing; DirectShow camera, CUDA)
- **Target:** Jetson AGX Orin 32GB, same code; config-level changes expected
  (faiss-gpu, V4L2 camera backend, TensorRT export are on the deployment
  checklist, not "zero changes")

## License & Governance

KaraOS is licensed under the **Apache License 2.0** (see [LICENSE](LICENSE) and [NOTICE](NOTICE)).

Governance model documented in [GOVERNANCE.md](GOVERNANCE.md). Contributor onboarding in [CONTRIBUTING.md](CONTRIBUTING.md). Community standards in [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
