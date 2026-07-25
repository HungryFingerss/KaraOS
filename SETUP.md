# KaraOS Setup Manual: from clone to a running system

KaraOS is a domain-agnostic embodied-presence runtime; this repo's default profile boots the companion, the first reference persona (the deployment shape is selected by `profiles/<name>.yaml` + `persona/<id>.yaml`, not baked into the engine).

**This manual was verified end-to-end on a fresh clone (2026-07-03):** every command below was actually run, in this order, on a machine that had never seen the repo, and the result was a working system (test suite: **4,233 passed / 0 failed** on a fresh CPU-only environment). If you follow the steps exactly, you end up in the same place.

**Platforms:** Windows, Linux, and macOS all get first-class instructions below
(every OS-specific command shows all three forms). Windows is the platform the
end-to-end verification ran on; Linux runs the full test suite in CI on every
push; macOS installs and runs the visual/memory stack but has no CUDA, and
[§4](#4-gpu-acceleration-and-what-cpu-only-machines-get) states plainly what
that means before you invest the time.

---

## 0. What you need before starting

| What | Why | Notes |
|---|---|---|
| **Python 3.13** | the runtime (3.11+ minimum; 3.13.5 is what the fresh-clone verification used) | `python --version` to check |
| **Git** | to clone | also needed DURING install, two dependencies install from pinned git forks |
| **Git-LFS** | the model weights (~600 MB) are LFS-stored | install below |
| **Node.js 18+** | ONLY for the optional web dashboard | skip if you don't want the dashboard |
| **Webcam + microphone** | the pipeline opens both at startup | laptop built-ins are fine |
| **A Together.ai API key** | powers the LLM + embeddings (free account: https://api.together.xyz to Settings to API Keys) | the system refuses to boot without it, loudly, with instructions |
| NVIDIA GPU (optional) | live speech-to-text + voice ID + faster vision | **NOT required to install or run** — the CPU-only path is verified working (that's what the fresh-clone run used). But the live *hearing* path currently needs CUDA; §4 explains exactly what CPU-only and macOS machines get |
| Ollama (optional) | local fallback LLM when the cloud is unreachable | `ollama pull qwen2.5:7b` |
| ~10 GB free disk | repo + weights (~1 GB) + venv (~6 GB) + auto-downloaded models (~3 GB) | |

Install Git-LFS once, system-wide:
- **Linux**: `sudo apt-get install git-lfs` (Fedora: `sudo dnf install git-lfs`)
- **macOS**: `brew install git-lfs`
- **Windows**: `winget install GitHub.GitLFS` (or https://git-lfs.com)

Then register it for your user (one-time): `git lfs install`

Audio note for Linux: recent `sounddevice` wheels bundle PortAudio, but if the
mic fails to open with a PortAudio error, install the system library:
`sudo apt-get install libportaudio2` (Fedora: `sudo dnf install portaudio`).
macOS and Windows need nothing extra.

---

## 1. Clone the repo

```bash
git clone https://github.com/HungryFingerss/KaraOS.git karaos
cd karaos
```

## 2. Pull the model weights (~600 MB)

```bash
git lfs pull
```

**Verify it worked**, the files must be real weights, not pointers:

```bash
# models/adaface_ir101.onnx should be ~206 MB, kokoro-v1.0.onnx ~310 MB.
# If any model file is ~130 BYTES, it's still an LFS pointer:
# run `git lfs install` then `git lfs pull` again.
```

## 3. Python environment: follow exactly

```bash
python -m venv venv

# Activate it:
# Windows (cmd): venv\Scripts\activate
# Windows (PowerShell): venv\Scripts\Activate.ps1
# Linux/macOS: source venv/bin/activate

# CRITICAL — do this BEFORE installing requirements:
python -m pip install --upgrade pip "setuptools<81" wheel
```

Why the `setuptools<81` line matters: two dependencies (the pinned speechbrain
+ pyannote forks) build from source, and their build imports `pkg_resources`,
which setuptools ≥ 81 removed. Skipping this line is the #1 way a fresh
install fails (`ModuleNotFoundError: No module named 'pkg_resources'`).

```bash
pip install -r requirements.txt
```

Takes ~5–15 minutes. Expected result: **0 errors** (the fresh-clone
verification installed all 26 dependencies, including both fork builds, clean).

## 4. GPU acceleration (and what CPU-only machines get)

Three paths. Pick yours.

### Windows + NVIDIA GPU

The default install gives you CPU-only PyTorch on Windows. Install the CUDA
build, `--force-reinstall` is REQUIRED here: plain `pip install torch` would
see the CPU torch from step 3 as "already satisfied" and silently do nothing
(found the hard way).

```bash
# RTX 50-series (Blackwell): cu128 · RTX 40/30-series: cu124 or cu121
pip install --force-reinstall torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

`onnxruntime-gpu` is already installed and picks up CUDA automatically once
the CUDA runtime libraries arrive with the torch install above.

### Linux + NVIDIA GPU

On Linux, `pip install torch` (step 3) already installs the CUDA build by
default, so most machines need **nothing extra** beyond a working NVIDIA
driver (`nvidia-smi` should print your GPU). If your driver needs a specific
CUDA line, use the same `--force-reinstall ... --index-url` command as the
Windows path with the matching `cu1xx` tag. `onnxruntime-gpu` is installed by
default on Linux and finds CUDA automatically. For Jetson, see
`deploy/README.md` (and swap `faiss-cpu` for `faiss-gpu`).

### macOS, or any machine without CUDA — what to expect, plainly

The install works: `requirements.txt` is platform-aware (macOS automatically
gets CPU `onnxruntime` instead of `onnxruntime-gpu`, which has no macOS
build), the camera uses the native AVFoundation backend, and the test suite is
fully verified on CPU (that's the 4,233/0 number). But KaraOS today is
CUDA-first at one specific spot, and you should know it before investing the
time:

**What runs well on CPU-only (including Apple Silicon):**
- Vision: face detection, recognition, tracking, anti-spoofing (CPU inference,
  a few FPS instead of ~30, fine for a desk setup)
- The voice OUT: Kokoro TTS speaks in near-real-time on CPU
- The brain: the LLM is a cloud call (Together.ai), identical on every machine
- All memory: the face/voice databases, the knowledge store, the graph, the
  dashboard, enrollment, factory reset
- The whole test suite and every CLI tool

**What does NOT work without CUDA (yet):**
- Live speech-to-text: Whisper is loaded with `device="cuda"` in the inference
  worker; on a no-CUDA machine it fails to load and the system simply never
  hears you (it degrades gracefully, no crash)
- Voice identification (ECAPA) and multi-speaker diarization (pyannote): same
  CUDA-gated loading path
- Apple's Metal/MPS is NOT used: the code checks `torch.cuda` only

**Practical meaning:** on a Mac (or any CPU-only box) you get a system that
*sees* you, recognizes your face, greets you by name, remembers you, and can
speak — but you cannot talk back to it by voice. A CPU/MPS fallback for the
hearing path is a tracked known limitation. For the full live experience,
including the system HEARING you, use a machine with an NVIDIA GPU for now.

## 5. API keys (.env)

```bash
# Windows:
copy .env.example .env
# Linux/macOS:
cp .env.example .env
```

Open `.env` in a text editor:

| Key | Required? | What it does |
|---|---|---|
| `TOGETHER_API_KEY` | **YES** | the LLM + embeddings. Without it the pipeline exits at boot with an error that tells you exactly how to fix it |
| `TAVILY_API_KEY` | optional | the web-search tool (skip = no live web answers) |
| `HF_TOKEN` | optional | multi-speaker diarization (pyannote). Also requires accepting the model license at https://huggingface.co/pyannote/speaker-diarization-3.1. Skip = single-speaker works fully; simultaneous multi-speaker audio uses a simpler fallback |
| `GROQ_API_KEY` | optional | alternate LLM provider |
| `CAMERA_INDEX` | default `0` | which camera to open (try `1` if you have multiple) |
| `OLLAMA_MODEL` | default `qwen2.5:7b` | the offline-fallback model (only used if you run Ollama) |
| `PYTHON_PATH` | recommended | absolute path to your venv python (used by the dashboard's server-side scripts). Linux/macOS: `/home/you/karaos/venv/bin/python` · Windows: `C:\...\karaos\venv\Scripts\python.exe` |

## 6. Verify the install (recommended: 5 minutes)

```bash
python -m pytest --ignore=tests/test_brain_json_parser_hypothesis.py -q
```

Expected: **~4,233 passed, 0 failed** (a few more pass on a CUDA machine,
4,237, because some GPU-gated tests un-skip). ANY line starting with
`FAILED` means something in your environment is off. See Troubleshooting.

## 7. First run

```bash
python pipeline.py
```

What happens, in order, **the first boot is special**:

1. **Model downloads (~5 min, once).** Whisper, ECAPA-TDNN, the face-analysis
   models, the emotion classifier download from Hugging Face into your user
   cache (`~/.cache/huggingface`). Every later boot reuses the cache. There is
   no "Apply the pyannote dependency patches" step for you: they live inside the
   pinned vendored forks (background:
   `docs/architecture/CHAPTER_13_observability_evolution_plans_pyannote.md`).
2. **Worker pools warm** (the GPU/CPU inference subprocesses), camera + mic open.
3. **First-boot enrollment.** You start from zero. This repo never ships
   anyone's personal data, so there is no `faces/` database until YOU create
   it. The system asks your name by voice and captures your face for ~5
   seconds. You become the owner (best friend) of this instance.
4. `[Pipeline] All systems ready. Watching...`, walk into frame and it greets
   you by name. Talk to it. Memory persists across sessions.

Every subsequent boot skips step 3 and recognizes you directly.

## 8. Dashboard (optional)

```bash
cd karaos-dashboard
npm install
npm run dev
```

The **pipeline terminal** prints a one-time auth URL at boot (the dashboard is
token-protected). Open that URL once (it sets a session cookie) then use
http://localhost:3000. The dashboard binds to localhost only by default.

---

## What exists after setup (and where it came from)

| | Source |
|---|---|
| All source code + tests + CI workflows | git |
| Architecture docs (CLAUDE.md, docs/architecture/ chapter files + the thin redirect at everything_about_system.md) | git |
| Model weights (AdaFace, Kokoro, SCRFD, smart-turn, anti-spoof) | git-lfs (`git lfs pull`) |
| Classifier seed (`data/classifier_scenarios_seed.jsonl`) | git, the runtime builds its DB from it at first boot |
| `venv/` | created by you (step 3) |
| `.env` API keys | yours (step 5) |
| Auto-downloaded models (Whisper, ECAPA, …) | Hugging Face, first run (step 7) |
| **`faces/` (the people it knows, memories, conversation history** | **created fresh on YOUR machine at first boot. Never in git) this repo contains no one's personal data.** |

---

## Troubleshooting

**`pip install -r requirements.txt` fails with `pkg_resources` / build errors.**
You skipped the `setuptools<81` seed. Run
`python -m pip install --upgrade pip "setuptools<81" wheel`, then rerun the install.

**A model fails to load / a file in `models/` is ~130 bytes.**
Those are LFS pointer files, not weights. `git lfs install` then `git lfs pull`.
Still stuck: `git lfs fetch --all && git lfs checkout`.

**Boot exits with a `TOGETHER_API_KEY` error.**
Working as designed. Set the key in `.env` (step 5). The error message itself
contains the exact fix commands.

**"Whisper failed to load" / Hugging Face download errors on first run.**
Network or rate-limiting. First-run downloads need ~5 minutes on a good
connection; just rerun. If you set `HF_TOKEN`, confirm it has read access.

**pyannote returns 0 segments on multi-speaker audio.**
(Background: `docs/architecture/CHAPTER_13_observability_evolution_plans_pyannote.md`
section 194-section 197.) Multi-speaker diarization needs `HF_TOKEN` + the accepted model
license (step 5 table). Without them the system falls back to a simpler
two-speaker split by design. The historical file-level patches are NOT
something you apply anymore. They live in the pinned forks.

**"pyannote ReproducibilityWarning: TF32"**, cosmetic. Ignore.

**Camera won't open, or the wrong camera opens.**
Set `CAMERA_INDEX` in `.env` (0, 1, 2…). Close other apps holding the camera.
Never run two copies of the pipeline at once, one camera, one owner.

**macOS: camera or mic opens to a black frame / permission errors.**
macOS gates hardware per-app: System Settings → Privacy & Security →
Camera (and Microphone) → enable for your terminal app (Terminal/iTerm/VS
Code). The first run should trigger the permission prompt; if you denied it
once, you must re-enable it there manually.

**Linux: mic fails with a PortAudio error.**
`sudo apt-get install libportaudio2` (Fedora: `sudo dnf install portaudio`),
then re-activate the venv and rerun. Check the mic is visible with
`python -c "import sounddevice; print(sounddevice.query_devices())"`.

**macOS: `pip install -r requirements.txt` fails on `onnxruntime-gpu`.**
You're on an old checkout. `git pull` — requirements.txt is platform-aware
(macOS gets CPU `onnxruntime` automatically; there is no CUDA build for
macOS).

**Pipeline crashes on import with a Kuzu `IndexError: invalid unordered_map` .**
The graph DB is in an inconsistent state. Delete `faces/brain_graph` and
`faces/brain_graph.wal`, the system rebuilds them from `brain.db` on next
start (self-heal is built in).

**Tests fail at step 6.**
Run `python -m pytest -x -q` and read the first failure. With a correct
environment the suite is 4,233+ passing / 0 failed (verified on a fresh
clone, CPU-only, 2026-07-03). The `tests/test_brain_json_parser_hypothesis.py`
file is excluded from the standard invocation and runs fine separately.

---

## Reset / start over

- **Wipe the people/memories, keep the install:** `python tools/factory_reset.py`
  (dry-run by default, add `--confirm` to actually wipe). Or simply delete the
  `faces/` folder while the pipeline is stopped.
- **Full clean slate:** delete the clone and start from step 1.
