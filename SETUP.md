# Setup — restoring KaraOS / dog-ai on a new machine

This file documents the full restore flow if you've lost your previous machine and want to bring KaraOS back from the git backup.

The repo is private. You'll need a GitHub account that has read access to it.

---

## Prerequisites

| What | Why |
|---|---|
| Python 3.11+ | Required by `requirements.txt` (faster-whisper, transformers, kuzu) |
| Git | To clone the repo |
| Git-LFS | To pull large model files (auto-stored via LFS) |
| CUDA-capable GPU | Strongly recommended; CPU-only path works but is slow |
| Ollama (optional) | Local fallback LLM when cloud is unreachable |
| Microphone + camera | The pipeline opens both at startup |

Install Git-LFS once, system-wide:

- **Windows**: `winget install GitHub.GitLFS` (or download from https://git-lfs.com)
- **Linux**: `sudo apt-get install git-lfs` (or your distro equivalent)
- **macOS**: `brew install git-lfs`

After install: `git lfs install` (registers LFS hooks for your user account; one-time).

---

## Restore flow

```bash
# 1. Clone the private repo (you'll be prompted to authenticate)
git clone https://github.com/HungryFingerss/Cognitive-System.git dog-ai
cd dog-ai

# 2. Pull the LFS-stored model files (~573 MB total)
git lfs pull

# 3. Set up Python virtual environment
python -m venv venv
# Activate it:
#   Windows:  source venv/Scripts/activate
#   Linux/Mac: source venv/bin/activate

# 4. Install Python dependencies
pip install -r requirements.txt

# 4b. PyTorch — install separately for your GPU's CUDA version.
# RTX 50-series (sm_120 / Blackwell): cu128
# RTX 40 / 30 series: cu121 or cu124
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

# 5. Restore your API keys to .env
cp .env.example .env
# Open .env in a text editor and fill in each key from your password manager:
#   - TOGETHER_API_KEY (primary LLM provider)
#   - TAVILY_API_KEY (web search)
#   - HF_TOKEN (HuggingFace, for pyannote diarization model download)
#   - PYTHON_PATH (set to the venv python on this machine)

# 6. (Optional) Pull Ollama fallback model if you want offline-capable brain
ollama pull qwen2.5:7b

# 7. Run the pipeline
python pipeline.py
```

The first run will:
- Auto-download Whisper, ECAPA-TDNN, RetinaFace (buffalo_l), pyannote, E5-large, j-hartmann-emotion, and a few other HuggingFace-hosted models on first import.
- Apply the pyannote dependency patches (see `everything_about_system.md` Part XXXI for why).
- Open the camera, mic, and dashboard ports.

If everything is configured correctly: you'll see `[Pipeline] All systems ready. Watching...` and the system is ready to recognize you when you walk into frame.

---

## What's restored vs. what isn't

After the restore steps above, you have:

| | Restored? | How |
|---|---|---|
| All source code | Yes | from git |
| Architecture docs (CLAUDE.md, everything_about_system.md, KARAOS guides) | Yes | from git |
| Model weights (AdaFace, Kokoro, SCRFD, smart-turn, antispoof) | Yes | from git-lfs |
| Classifier scenarios DB (the 2,071 abstracted scenarios) | Yes | from git-lfs |
| Faces DB + voice profiles + your enrolled photo | Yes | from git |
| Brain knowledge graph (Kuzu DB) — your conversation memory | Yes | from git-lfs |
| FAISS face index | Yes | from git-lfs |
| API keys | NO — you fill in `.env` from your password manager |
| Auto-downloaded models (Whisper, ECAPA, etc.) | NO — re-downloaded on first pipeline run |
| `venv/` virtual environment | NO — recreated by `python -m venv venv` + pip install |
| Live session logs (`terminal_output_*.md`) | NO — these are gitignored for privacy |

---

## Troubleshooting

**"git lfs pull" hangs or fails.** Check that you have `git lfs install` configured. If on a metered connection, `git lfs pull --include="models/*.onnx"` to pull selectively.

**Pipeline crashes on import with `IndexError: invalid unordered_map<K, T> key` (Kuzu).** The Kuzu graph DB might be in an inconsistent state from the previous machine. Delete `faces/brain_graph` and `faces/brain_graph.wal` — the system will rebuild from `brain.db` on next start (Session 58 self-heal logic).

**"Whisper failed to load" or "ECAPA failed to load."** You probably have HuggingFace rate-limiting, or no network access. Check `HF_TOKEN` is set and has read access. First-run downloads need ~5 minutes on a good connection.

**"pyannote ReproducibilityWarning: TF32 disabled"** — cosmetic. Ignore.

**"pyannote returns 0 segments on multi-speaker audio."** Run `python tests/patch_pyannote_io.py` to reapply the file-level patches (see `everything_about_system.md` §195). These patches are mandatory after any `pip install pyannote.audio`.

**"`models/X.onnx` not found"** even after git lfs pull. Run `git lfs ls-files` to verify which files are LFS-tracked. Run `git lfs fetch --all` then `git lfs checkout` to force-restore.

**Tests fail.** Run `pytest -x` and look at the first failure. The test suite is 1374 passing as of 2026-05-02; if anything fails, it's likely an environment issue (missing GPU, missing models, missing API keys for tests that hit real APIs).

---

## What to verify after restore

1. `pytest` — should report ~1374 passing, 2 skipped.
2. `python pipeline.py` — should reach `[Pipeline] All systems ready. Watching...` within ~30 seconds.
3. Walk into camera frame as the enrolled best_friend (Jagan). System should greet you by name within ~2 seconds.
4. Have a short conversation. Memory should persist across sessions (ask "what did we talk about yesterday" — should retrieve from `brain.db`).

If all four checks pass, the restore is complete and the system is at the same state as the previous machine.
