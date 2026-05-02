"""Apply known compat patches to pyannote.audio 3.3.2 for our torch/HF stack.

Context (Session 88, 2026-04-22):
  torchaudio 2.9+ removed several legacy audio-backend APIs that pyannote
  3.x relies on. huggingface_hub renamed ``use_auth_token`` → ``token``.
  pyannote's maintainers have not shipped a torchaudio 2.9+ compat release
  (upstream issue #1974 open, unanswered). Our production torch is 2.10;
  downgrading is forbidden (cascade-breaks faster-whisper + SpeechBrain
  per reviewer's Session 88 call).

  This script applies three surgical edits to the installed pyannote.audio
  site-packages files:

    1. (io.py)  ``-> torchaudio.AudioMetaData:`` → ``-> object:``
       (AudioMetaData removed in torchaudio 2.9; the annotation is
       runtime-irrelevant — only used in type hints — so Python object is
       a safe replacement.)

    2. (io.py)  ``torchaudio.list_audio_backends()`` →
       ``getattr(torchaudio, 'list_audio_backends', lambda: ['sox_io'])()``
       (list_audio_backends removed in torchaudio 2.9; the fallback
       returns ``['sox_io']`` which pyannote accepts as a sentinel — it
       means "some backend is available, proceed" because our actual
       audio path is in-memory tensors from sounddevice, NOT file I/O.)

    3. (pipeline.py)  ``use_auth_token=use_auth_token,`` →
       ``token=use_auth_token,``
       (huggingface_hub renamed the kwarg; pyannote 3.3.2 still passes
       the old name to ``hf_hub_download(...)``. Only patches the one
       call-site-shaped match — not line 137's ``params.setdefault``
       dict-key usage, which feeds pyannote's own inner class.)

    4. (speechbrain/utils/torch_audio_backend.py) same
       ``list_audio_backends()`` rewrite as Patch 2. pyannote's speaker
       verification module imports SpeechBrain, which also calls the
       removed API at module-load. Our existing ``core/voice.py`` has a
       runtime monkeypatch for this, but it only fires if voice.py is
       imported before pyannote. Patching at the file level makes import
       order irrelevant.

    5. (pyannote/audio/tasks/segmentation/mixins.py)
       ``from torchaudio import AudioMetaData`` →
       try/except shim that defines a stub class if torchaudio doesn't
       have it. The class is only used in ``SegmentationTask.get_file()``
       which runs during training; inference never touches it, so the
       stub is functionally safe for our dispatch path.

    6. (pyannote/audio/utils/protocol.py) same ``list_audio_backends()``
       rewrite as Patch 2. Hit by the Pipeline loading chain via
       ``tasks.segmentation`` → ``utils.protocol``.

    7. (pyannote/audio/core/model.py) pass ``weights_only=False`` to
       ``pl_load``. torch 2.6+ flipped ``torch.load``'s default
       ``weights_only`` from False to True, which trips
       ``UnpicklingError: Unsupported global: TorchVersion`` on pyannote
       checkpoints. Pyannote's models are HF-hosted and license-gated
       (safe source), so ``weights_only=False`` is appropriate here.
       lightning_fabric's own ``_load`` already does this fallback for
       remote URLs but not for local file paths — pyannote passes the
       downloaded-file path which hits the stricter branch.

Usage:
  Run manually after every pip install / reinstall of pyannote.audio:

    python tests/patch_pyannote_io.py

  The script is idempotent — it detects if the patches are already in place
  and exits cleanly without writing. Safe to run multiple times.

Fallback:
  If pyannote still crashes on actual audio processing (runtime, not just
  import), pivot to Option D — SpeechBrain's built-in diarization recipe —
  as reviewer's Session 88 fallback plan. SpeechBrain is already in our
  venv for ECAPA-TDNN and has better torch 2.x compat.

Sources:
  - https://github.com/pyannote/pyannote-audio/issues/1952 (AudioMetaData)
  - https://github.com/jhj0517/Whisper-WebUI/issues/613 (community workaround)
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

# NOTE: we intentionally do NOT ``import pyannote.audio`` — the import is
# exactly the thing we're patching, so it would fail at
# ``torchaudio.AudioMetaData`` before this script could run. ``find_spec``
# locates the module path without executing any of its code.
spec = importlib.util.find_spec("pyannote.audio")
if spec is None or spec.origin is None:
    print("[patch] pyannote.audio not installed (find_spec returned None)", file=sys.stderr)
    sys.exit(1)

pyannote_root = pathlib.Path(spec.origin).parent
core_dir      = pyannote_root / "core"
io_py         = core_dir / "io.py"
pipeline_py   = core_dir / "pipeline.py"
inference_py  = core_dir / "inference.py"
model_py      = core_dir / "model.py"
mixins_py     = pyannote_root / "tasks" / "segmentation" / "mixins.py"
protocol_py   = pyannote_root / "utils" / "protocol.py"
for target in (io_py, pipeline_py, inference_py, model_py, mixins_py, protocol_py):
    if not target.exists():
        print(f"[patch] target file not found: {target}", file=sys.stderr)
        sys.exit(1)

# ── Patches 1 + 2 — core/io.py torchaudio compat ─────────────────────────────
io_text = io_py.read_text(encoding="utf-8")
io_orig = io_text

# Patch 1: AudioMetaData removed in torchaudio 2.9+.
io_text = io_text.replace("-> torchaudio.AudioMetaData:", "-> object:")

# Patch 2: list_audio_backends() removed in torchaudio 2.9+.
io_text = io_text.replace(
    "torchaudio.list_audio_backends()",
    "getattr(torchaudio, 'list_audio_backends', lambda: ['sox_io'])()",
)

if io_text == io_orig:
    print(f"[patch] io.py: no changes needed — already patched (or unexpected shape).")
else:
    io_py.write_text(io_text, encoding="utf-8")
    print(f"[patch] io.py: applied 2 torchaudio compat patches")

# ── Patch 3 — core/pipeline.py huggingface_hub kwarg rename ──────────────────
pl_text = pipeline_py.read_text(encoding="utf-8")
pl_orig = pl_text

# Patch 3: huggingface_hub renamed use_auth_token → token. Only matches the
# one call-site shape "use_auth_token=use_auth_token," (comma at end) —
# which is the hf_hub_download() call, not the dict-key setdefault on line
# 137 which feeds pyannote's own inner Pipeline class.
pl_text = pl_text.replace(
    "use_auth_token=use_auth_token,",
    "token=use_auth_token,",
)

if pl_text == pl_orig:
    print(f"[patch] pipeline.py: no changes needed — already patched (or unexpected shape).")
else:
    pipeline_py.write_text(pl_text, encoding="utf-8")
    print(f"[patch] pipeline.py: applied 1 huggingface_hub kwarg-rename patch")

# Patch 3 continued — same kwarg-rename in inference.py + model.py. These
# are the other two files in core/ that directly call hf_hub_download. The
# trailing-comma match uniquely picks the call-site shape and skips all
# the get_model(...) inter-pyannote call sites (which don't hit
# huggingface_hub directly — their use_auth_token flows down into these
# three files eventually).
for target in (inference_py, model_py):
    t_text = target.read_text(encoding="utf-8")
    t_orig = t_text
    t_text = t_text.replace(
        "use_auth_token=use_auth_token,",
        "token=use_auth_token,",
    )
    label = target.name
    if t_text == t_orig:
        print(f"[patch] {label}: no changes needed — already patched.")
    else:
        target.write_text(t_text, encoding="utf-8")
        n = t_orig.count("use_auth_token=use_auth_token,")
        print(f"[patch] {label}: applied {n} huggingface_hub kwarg-rename patch(es)")

# ── Patches 5 + 6 — additional pyannote sites surfaced during verification ──
#
# The first patch round covered core/io.py and core/pipeline.py; Pipeline
# construction then dove into tasks/segmentation and utils/protocol which
# both have their own calls to the removed torchaudio APIs. We keep adding
# file-level patches rather than moving to a runtime monkeypatch because
# file edits persist across subprocess calls — critical when the bench or
# pyannote's own internals spawn workers.
mixins_text = mixins_py.read_text(encoding="utf-8")
mixins_orig = mixins_text
# Patch 5: import-time shim for AudioMetaData. Wrap the direct import in a
# try/except that defines a stub when torchaudio doesn't expose it. The
# stub is only hit in training paths (SegmentationTask.get_file), which
# our inference-only dispatch never enters.
#
# IDEMPOTENCY: we can't just string-replace the bare import line because
# the try: body still contains that exact line after the first run —
# so a second run would re-wrap it and produce a nested try/try mess.
# Gate the replacement on a sentinel marker present ONLY in the patched
# form. The marker is inside the comment we control, so upstream updates
# won't accidentally trip it.
_SHIM_MARKER = "# torchaudio 2.9+ removed AudioMetaData. Stub it"
_old_import = "from torchaudio import AudioMetaData"
_new_import = (
    "try:\n"
    "    from torchaudio import AudioMetaData\n"
    "except ImportError:\n"
    "    # torchaudio 2.9+ removed AudioMetaData. Stub it — only used in\n"
    "    # SegmentationTask.get_file() (training path), never at inference.\n"
    "    class AudioMetaData:\n"
    "        def __init__(self, **kwargs): self.__dict__.update(kwargs)"
)
if _SHIM_MARKER in mixins_text:
    print(f"[patch] mixins.py: no changes needed — sentinel already present.")
else:
    mixins_text = mixins_text.replace(_old_import, _new_import, 1)   # count=1 extra safety
    if mixins_text == mixins_orig:
        print(f"[patch] mixins.py: no AudioMetaData import found (unexpected shape).")
    else:
        mixins_py.write_text(mixins_text, encoding="utf-8")
        print(f"[patch] mixins.py: applied AudioMetaData import shim")

protocol_text = protocol_py.read_text(encoding="utf-8")
protocol_orig = protocol_text
# Patch 6: same list_audio_backends fallback as Patch 2, different file.
protocol_text = protocol_text.replace(
    "torchaudio.list_audio_backends()",
    "getattr(torchaudio, 'list_audio_backends', lambda: ['sox_io'])()",
)
if protocol_text == protocol_orig:
    print(f"[patch] protocol.py: no changes needed — already patched.")
else:
    protocol_py.write_text(protocol_text, encoding="utf-8")
    print(f"[patch] protocol.py: applied list_audio_backends fallback")

# ── Patch 7 — torch 2.6+ weights_only default change ─────────────────────────
# pyannote's core/model.py loads checkpoints via two paths, both of which
# default torch.load's weights_only to True post-torch-2.6 and crash on
# pyannote's TorchVersion-containing checkpoints. Pyannote's checkpoints
# are HF-hosted and license-gated (safe source), so weights_only=False is
# the appropriate trust level here.
#   (a) pl_load(path_for_pl, map_location=map_location) at line 671
#   (b) Klass.load_from_checkpoint(path_for_pl, map_location=..., strict=...,
#       **kwargs) at line 678 — the one actually hit during inference.
model_text = model_py.read_text(encoding="utf-8")
model_orig = model_text
# Path (a): add weights_only=False to the pl_load call. (Was previously the
# only path patched; live run surfaced that load_from_checkpoint is the
# real one that fires.)
model_text = model_text.replace(
    "pl_load(path_for_pl, map_location=map_location)",
    "pl_load(path_for_pl, map_location=map_location, weights_only=False)",
)
# Path (b): load_from_checkpoint — inject weights_only=False into the
# kwargs line since pytorch_lightning's load_from_checkpoint accepts it
# and passes through to pl_load internally. Use the unique ``strict=strict,``
# arg line as the anchor; inserting on the next line keeps indentation
# aligned.
_old_lfc = "                strict=strict,\n                **kwargs,"
_new_lfc = "                strict=strict,\n                weights_only=False,\n                **kwargs,"
model_text = model_text.replace(_old_lfc, _new_lfc)
if model_text == model_orig:
    print(f"[patch] model.py (weights_only): no changes needed — already patched.")
else:
    model_py.write_text(model_text, encoding="utf-8")
    print(f"[patch] model.py: applied weights_only=False to pl_load + load_from_checkpoint")

# ── Patch 4 — speechbrain torch_audio_backend list_audio_backends ────────────
# pyannote.audio.pipelines.speaker_verification imports speechbrain, which
# also crashes on torchaudio.list_audio_backends(). core/voice.py has a
# runtime monkeypatch but only works if voice.py is imported before pyannote.
# File-level patch removes the import-order dependency entirely.
sb_spec = importlib.util.find_spec("speechbrain")
if sb_spec is not None and sb_spec.origin is not None:
    sb_tab = pathlib.Path(sb_spec.origin).parent / "utils" / "torch_audio_backend.py"
    if sb_tab.exists():
        sb_text = sb_tab.read_text(encoding="utf-8")
        sb_orig = sb_text
        sb_text = sb_text.replace(
            "torchaudio.list_audio_backends()",
            "getattr(torchaudio, 'list_audio_backends', lambda: ['sox_io'])()",
        )
        if sb_text == sb_orig:
            print(f"[patch] speechbrain: no changes needed — already patched.")
        else:
            sb_tab.write_text(sb_text, encoding="utf-8")
            print(f"[patch] speechbrain: applied list_audio_backends fallback patch")
    else:
        print(f"[patch] speechbrain: target file not found at {sb_tab} (skipping)")
else:
    print("[patch] speechbrain: not installed (skipping)")
