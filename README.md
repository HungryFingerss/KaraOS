# KaraOS (`dog-ai`)

![fast CI](https://github.com/jagannivas/dog-ai/actions/workflows/fast.yml/badge.svg)
![nightly CI](https://github.com/jagannivas/dog-ai/actions/workflows/slow.yml/badge.svg)
![security scan](https://github.com/jagannivas/dog-ai/actions/workflows/security.yml/badge.svg)

KaraOS is a domain-agnostic embodied-presence runtime — the cognitive layer for
an embodied AI agent: it sees, hears, recognizes people, remembers them across
sessions, and holds spoken conversations. What it deploys AS is selected by a
profile + persona pack (`profiles/` + `persona/`); the companion — this repo's
default profile — is the first reference persona:
see face → identify → greet → listen → respond → repeat.

## Structure

```
dog-ai/
├── core/
│   ├── config.py      # all settings
│   ├── vision.py      # RetinaFace detection + AdaFace recognition
│   ├── db.py          # SQLite + FAISS face database
│   ├── brain.py       # Gemini (primary) + Ollama (fallback)
│   ├── audio.py       # Whisper STT + edge-tts TTS
│   └── state.py       # shared state (pipeline → dashboard)
├── dog-ai-dashboard/  # Next.js dashboard
├── pipeline.py        # main loop
├── enroll.py          # standalone enrollment script
├── delete_person.py   # delete a person
├── models/            # place ONNX models here (see below)
├── faces/             # face DB (auto-created, gitignored)
└── requirements.txt
```

## Setup

### 1. Python environment

```bash
python -m venv venv
venv\Scripts\activate       # Windows
pip install -r requirements.txt
```

### 1a. Pre-commit hook (P0.S6 secrets-scanning)

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

### 2. Download models

Place these in `models/`:
- `scrfd_10g_bnkps.onnx` — from: https://github.com/deepinsight/insightface
- `adaface_ir101.onnx`   — from: https://github.com/mk-minchul/AdaFace

### 3. Environment variables

```bash
copy .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### 4. Dashboard

```bash
cd dog-ai-dashboard
npm install
npm run dev     # development
npm run build   # production
npm start
```

Dashboard runs on http://localhost:3000

### 5. Run pipeline

```bash
# From dog-ai/ root
python pipeline.py
```

## Enrollment

**Voice:** Say "add me", "enroll me", "remember me" to the system.
It asks your name then captures your face for 5 seconds.

**Manual:** Go to http://localhost:3000/enroll, enter name, click start.

**Script:** `python enroll.py --name "Your Name"`

## Hardware targets

- **Now:** Laptop (development + testing)
- **Later:** Jetson AGX Orin 32GB (drop-in, same code, zero changes)

## License & Governance

KaraOS is licensed under the **Apache License 2.0** (see [LICENSE](LICENSE) and [NOTICE](NOTICE)).

Governance model documented in [GOVERNANCE.md](GOVERNANCE.md). Contributor onboarding in [CONTRIBUTING.md](CONTRIBUTING.md). Community standards in [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
