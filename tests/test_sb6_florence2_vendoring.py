"""SB.6 Step 1 — Florence-2 vendoring anchors (supply-chain lock).

Validates that Florence-2 is loaded from the vendored `core/_florence2/` package — NOT
trust_remote_code against the HuggingFace hub. The vendored modeling code is under review
and pinned to a recorded SHA; loading it via a local package import (rather than letting
`from_pretrained(..., trust_remote_code=True)` fetch+exec arbitrary modeling code from the
hub at runtime) is the supply-chain guarantee.

Anchor surface (mirrors the P0.R5 vendored-pyannote test):
- Structural anchors (always run): wrapper __init__.py exists + re-exports the 3 classes;
  LICENSE (MIT) present; the 3 vendored .py keep their upstream Apache-2.0 template headers
  and carry NO KaraOS SPDX tag (Resolution C — the SPDX sweep excludes this dir); `timm`
  declared in requirements.txt.
- Behavioral import-anchor (skips cleanly when torch/transformers/timm absent): the package
  imports + each re-exported class resolves to a `core._florence2.*` module. The `__module__`
  assertion is the LOAD-BEARING supply-chain lock — a revert to a hub trust_remote_code load
  would resolve the class to `transformers_modules.microsoft.Florence-2-large.<sha>.*`, which
  this anchor would catch.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_FLORENCE_DIR = _REPO_ROOT / "core" / "_florence2"

# Common substring across all three vendored .py (HuggingFace transformers template header).
_APACHE_HEADER = '# Licensed under the Apache License, Version 2.0 (the "License");'
# The KaraOS authorship tag the SPDX sweep stamps onto OUR code — must be ABSENT from vendored code.
_KARAOS_SPDX = "# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors"

_VENDORED_MODULES = (
    "configuration_florence2.py",
    "modeling_florence2.py",
    "processing_florence2.py",
)

# (re-exported class name, vendored module it must resolve to)
_REEXPORTS = (
    ("Florence2Config", "core._florence2.configuration_florence2"),
    ("Florence2ForConditionalGeneration", "core._florence2.modeling_florence2"),
    ("Florence2Processor", "core._florence2.processing_florence2"),
)


# ---------------------------------------------------------------------------
# Structural anchors (always run)
# ---------------------------------------------------------------------------


def test_sb6_wrapper_init_exists_and_reexports() -> None:
    """A1 — core/_florence2/__init__.py exists and re-exports the 3 classes via __all__."""
    init = _FLORENCE_DIR / "__init__.py"
    assert init.is_file(), f"vendored Florence-2 wrapper missing at {init}"
    src = init.read_text(encoding="utf-8")
    for name, _module in _REEXPORTS:
        assert name in src, f"__init__.py must re-export {name}"
    # NO machine SPDX tag on the wrapper (Resolution C — the dir is excluded from the sweep).
    assert _KARAOS_SPDX not in src, (
        "core/_florence2/__init__.py must NOT carry the KaraOS SPDX tag — the vendored "
        "directory is EXCLUDED from tools/add_spdx_headers.py (SB.6 Resolution C)"
    )


def test_sb6_license_present_and_mit() -> None:
    """A2 — core/_florence2/LICENSE exists (MIT, Microsoft repo-level)."""
    lic = _FLORENCE_DIR / "LICENSE"
    assert lic.is_file(), f"vendored Florence-2 LICENSE missing at {lic}"
    assert "MIT License" in lic.read_text(encoding="utf-8"), (
        "core/_florence2/LICENSE must be the upstream MIT license (Microsoft repo-level)"
    )


@pytest.mark.parametrize("module", _VENDORED_MODULES)
def test_sb6_vendored_file_keeps_apache_header_no_karaos_tag(module: str) -> None:
    """A3 — each vendored .py keeps its upstream Apache-2.0 template header and carries
    NO KaraOS SPDX tag (proves Resolution C: vendored license headers preserved byte-for-byte,
    the sweep does not stamp them)."""
    path = _FLORENCE_DIR / module
    assert path.is_file(), f"vendored Florence-2 module missing at {path}"
    src = path.read_text(encoding="utf-8")
    assert _APACHE_HEADER in src, (
        f"{module} must keep its upstream Apache-2.0 template header verbatim"
    )
    assert _KARAOS_SPDX not in src, (
        f"{module} must NOT carry the KaraOS SPDX tag — vendored third-party code keeps "
        f"its own license; tools/add_spdx_headers.py excludes core/_florence2/"
    )


def test_sb6_timm_declared_in_requirements() -> None:
    """A4 — timm (DaViT vision backbone for Florence-2) declared in requirements.txt."""
    reqs = (_REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "timm" in reqs, (
        "requirements.txt must declare timm — the vendored Florence-2 modeling code imports "
        "timm layers for the DaViT vision backbone"
    )


# ---------------------------------------------------------------------------
# Behavioral import-anchor (the supply-chain lock; skips when deps absent)
# ---------------------------------------------------------------------------


def test_sb6_florence2_loads_from_vendored_package_not_hub() -> None:
    """A5 — the 3 classes import from core._florence2 and resolve to core._florence2.* modules.

    The `__module__` assertion is the LOAD-BEARING supply-chain lock: a class loaded via a hub
    `from_pretrained(..., trust_remote_code=True)` download would resolve to
    `transformers_modules.microsoft.Florence-2-large.<sha>.*`, NOT `core._florence2.*`. This
    anchor catches any revert to the trust_remote_code path.

    Skips cleanly on boxes without torch/transformers/timm (the modeling code imports all three).
    """
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    pytest.importorskip("timm")

    import importlib

    pkg = importlib.import_module("core._florence2")

    assert set(getattr(pkg, "__all__", ())) == {name for name, _m in _REEXPORTS}, (
        "core/_florence2/__init__.py __all__ must be exactly the 3 re-exported classes"
    )

    for name, expected_module in _REEXPORTS:
        cls = getattr(pkg, name, None)
        assert cls is not None, f"core._florence2 must export {name}"
        assert cls.__module__ == expected_module, (
            f"SUPPLY-CHAIN VIOLATION: {name} resolved to {cls.__module__!r}, expected "
            f"{expected_module!r}. The class must load from the vendored package — a "
            f"trust_remote_code hub load would land it in transformers_modules.*."
        )
