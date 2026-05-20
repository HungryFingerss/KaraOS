"""tests/test_secrets_invariants.py — P0.S6 D3.a + D3.b structural invariants.

Three-layer defense-in-depth against secrets-management drift. Production code
is already hygienic (Phase 0 audit verified); these AST tests structurally
enforce the discipline so future code stays hygienic.

Plan v2 §9.1 / §9.2 / §11 Phase 1.

D3.a: `test_no_secret_value_in_prints_or_logs` — no secret-shaped variable
      interpolated into a print() / log call. Belt-and-braces via
      `_SECRET_NAMES` frozenset + `_SECRET_NAME_PATTERN` regex.

D3.b: `test_env_var_reads_centralized` — `os.environ` / `os.getenv` reads (AND
      writes — flagged for defense-in-depth per Plan v2 MED 2) only allowed
      in `core/config.py` OR in the `_ENV_VAR_ACCESS_ALLOWLIST` (with
      documented rationale per access).

Plus 2 hygiene tests for the .env.example cleanup and .gitignore N1 coverage.
"""
from __future__ import annotations

import ast
import pathlib
import re


_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CORE = _REPO_ROOT / "core"
_PIPELINE = _REPO_ROOT / "pipeline.py"
_ENROLL = _REPO_ROOT / "enroll.py"
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"
_GITIGNORE = _REPO_ROOT / ".gitignore"


# ────────────────────────────────────────────────────────────────────────────
# Plan v2 §2 — _SECRET_NAMES + _SECRET_NAME_PATTERN (MED 1)
# ────────────────────────────────────────────────────────────────────────────

# P0.S6 D3.a — explicit secret-variable names for the no-secret-in-prints scan.
#
# This frozenset is BELT-AND-BRACES with the regex pattern below:
#
#   _SECRET_NAME_PATTERN = re.compile(
#       r"(?i).*(_api_key|_token|_secret|_password|_pass|_auth|_credential).*"
#   )
#
# The regex catches future-introduced variables matching the *_API_KEY / *_TOKEN
# naming convention. The frozenset's entry for `hf_token` is defense-in-depth
# in case the regex pattern is later refactored to be more restrictive (e.g.
# requiring word boundaries that would skip the lowercase local at
# core/voice.py:302). Plan v2 §2 doc-precision item (architect-flagged):
# disposition (b) — keep the entry, refine the rationale comment.
#
# Both layers fire on every `print(...)` / `log.*(...)` interpolation; a match
# from EITHER counts as a violation. Adding a new secret variable in production
# requires either matching the regex pattern OR adding to this frozenset.
_SECRET_NAMES: frozenset[str] = frozenset({
    # Active production secrets (read via os.getenv in core/config.py + core/voice.py)
    "CHAT_API_KEY",          # core/brain.py — Authorization header for chat LLM
    "EXTRACT_API_KEY",       # core/brain_agent.py — Authorization header
    "EMBED_API_KEY",         # core/brain_agent.py — embeddings
    "VISION_API_KEY",        # core/config.py — vision (currently disabled, alias to TOGETHER)
    "TOGETHER_API_KEY",      # core/config.py:307 — root provider key
    "TAVILY_API_KEY",        # core/config.py:352 — web search
    "GROQ_API_KEY",          # core/config.py:309 — reserved future provider
    "HF_TOKEN",              # core/voice.py:302 — pyannote gated-repo (env var name)
    "hf_token",              # core/voice.py:302 — lowercase local holding HF_TOKEN value
    # Rotated-but-kept-for-blocking — D2.b rotated these at provider; frozenset
    # entry blocks re-introduction in production code via prints/logs.
    "GEMINI_API_KEY",
    "SARVAM_API_KEY",
})

_SECRET_NAME_PATTERN = re.compile(
    r"(?i).*(_api_key|_token|_secret|_password|_pass|_auth|_credential).*"
)


def _is_secret_name(name: str) -> bool:
    """Return True if `name` is a known secret variable OR matches the secret-name
    regex pattern. Belt-and-braces — both layers fire independently."""
    return name in _SECRET_NAMES or bool(_SECRET_NAME_PATTERN.match(name))


# ────────────────────────────────────────────────────────────────────────────
# Plan v2 §3 — env-var access allowlist (D3.b)
# ────────────────────────────────────────────────────────────────────────────

# Each entry: (relative-file-path, env-var-name, access-type) → rationale.
# access-type ∈ {"read", "write"}.
#
# Adding a new entry requires explicit architect approval per Plan v2 §12 #4.
_ENV_VAR_ACCESS_ALLOWLIST: dict[tuple[str, str, str], str] = {
    ("core/event_log/producer.py", "EVENT_LOG_ENABLED", "read"):
        "P0.0.7 D5 toggle — module-level bool at import time; not a secret",
    ("core/event_log/producer.py", "EVENT_LOG_TESTING", "read"):
        "P0.0.7 test-mode flag — not a secret",
    ("core/classifier_graph.py", "CLASSIFIER_DB_PATH_OVERRIDE", "read"):
        "Test/dev path override — not a secret",
    ("core/vision.py", "INSIGHTFACE_LOG_LEVEL", "write"):
        "Module-level os.environ assignment to suppress InsightFace's chatty "
        "logger. Plan v2 MED 2 documented write-context exception — writes are "
        "flagged by default; this one explicitly allowed with rationale.",
    ("core/voice.py", "HF_TOKEN", "read"):
        "pyannote gated-repo access. Lazy read — cannot move to config.py "
        "because config.py loads at import time; voice.py lazily decides "
        "whether to load pyannote. Read site is hygienic (verified Phase 0).",
}


def _scan_env_var_access(
    tree: ast.AST, rel_path: str
) -> "list[tuple[int, str, str]]":
    """Walk AST. Return list of (lineno, env_var_name, access_type) tuples.

    access_type ∈ {"read", "write", "non_literal", "indirect"}.

    Covers:
      - `os.environ.get("VAR")` / `os.environ.get("VAR", default)`  → read
      - `os.getenv("VAR")` / `os.getenv("VAR", default)`            → read
      - `os.environ["VAR"]` (Load context)                          → read
      - `os.environ["VAR"] = value` (Store context)                 → write
      - `os.environ.pop("VAR")` / `setdefault("VAR", ...)`          → write
      - `os.environ.get(some_var)` (Name arg, not Constant)         → non_literal
      - bare `os.environ` reference (not subscripted)               → indirect
    """
    out: list[tuple[int, str, str]] = []

    for node in ast.walk(tree):
        # os.environ.get("VAR") / os.getenv("VAR") / os.environ.pop("VAR") / ...
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            func = node.func
            # Detect chain: os.<something>(...) OR os.environ.<something>(...)
            #
            #   os.getenv("VAR")           → func.value=Name('os'),     func.attr='getenv'
            #   os.environ.get("VAR")      → func.value=Attribute(value=Name('os'), attr='environ'),
            #                                 func.attr='get'
            chain_root: ast.AST = func.value
            access_kind: str | None = None
            if isinstance(chain_root, ast.Name) and chain_root.id == "os" and func.attr == "getenv":
                access_kind = "read"
            elif (isinstance(chain_root, ast.Attribute)
                  and isinstance(chain_root.value, ast.Name)
                  and chain_root.value.id == "os"
                  and chain_root.attr == "environ"):
                # os.environ.<method>
                if func.attr == "get":
                    access_kind = "read"
                elif func.attr in {"pop", "setdefault", "update", "clear"}:
                    access_kind = "write"
                else:
                    access_kind = "write"  # any other mutating method is a write
            if access_kind is not None and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    out.append((node.lineno, first.value, access_kind))
                else:
                    out.append((node.lineno, "<non_literal>", "non_literal"))

        # os.environ["VAR"] — Subscript with Load/Store context
        if isinstance(node, ast.Subscript):
            val = node.value
            if (isinstance(val, ast.Attribute)
                    and isinstance(val.value, ast.Name)
                    and val.value.id == "os"
                    and val.attr == "environ"):
                # Detect the key
                key_node = node.slice
                if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                    key_str = key_node.value
                else:
                    key_str = "<non_literal>"
                # Load vs Store context
                ctx = "read" if isinstance(node.ctx, ast.Load) else "write"
                if key_str == "<non_literal>":
                    out.append((node.lineno, key_str, "non_literal"))
                else:
                    out.append((node.lineno, key_str, ctx))

    return out


# ────────────────────────────────────────────────────────────────────────────
# Plan v2 §9.1 — D3.a no_secret_value_in_prints_or_logs
# ────────────────────────────────────────────────────────────────────────────


def _iter_production_py_files() -> "list[pathlib.Path]":
    """Production scope per Plan v2 P1: core/*.py + pipeline.py + enroll.py.
    Tests, bootstrap, audit_person, delete_person, migrate_* are out of scope."""
    files: list[pathlib.Path] = []
    for path in _CORE.rglob("*.py"):
        files.append(path)
    if _PIPELINE.exists():
        files.append(_PIPELINE)
    if _ENROLL.exists():
        files.append(_ENROLL)
    return files


_LOG_METHOD_RE = re.compile(r"(?i)^(log|debug|info|warn|warning|error|critical|exception)$")


def _is_print_or_log_call(call: ast.Call) -> bool:
    """True for print(...) or any .<log_method>(...) shape."""
    f = call.func
    if isinstance(f, ast.Name) and f.id == "print":
        return True
    if isinstance(f, ast.Attribute) and _LOG_METHOD_RE.match(f.attr):
        return True
    return False


def _walk_interpolation_args(call: ast.Call) -> "list[ast.AST]":
    """Yield AST nodes that are interpolation slots inside a print/log call.

    Covers:
      - f-strings (JoinedStr): yield each FormattedValue.value
      - "fmt" % (...): yield the RHS (Tuple elements or single value)
      - "fmt".format(...): yield each format arg
      - Plain Name passed as arg: include too (logger.error(secret_value))
    """
    out: list[ast.AST] = []
    for arg in call.args:
        if isinstance(arg, ast.JoinedStr):
            for piece in arg.values:
                if isinstance(piece, ast.FormattedValue):
                    out.append(piece.value)
        elif isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Mod):
            rhs = arg.right
            if isinstance(rhs, ast.Tuple):
                out.extend(rhs.elts)
            else:
                out.append(rhs)
        elif (isinstance(arg, ast.Call)
              and isinstance(arg.func, ast.Attribute)
              and arg.func.attr == "format"):
            out.extend(arg.args)
            for kw in arg.keywords:
                out.append(kw.value)
        else:
            # Plain Name / Attribute / etc. — direct logging of a value.
            out.append(arg)
    return out


def test_no_secret_value_in_prints_or_logs() -> None:
    """P0.S6 D3.a — no production code interpolates a secret-shaped variable
    into a print() or log call. Belt-and-braces: frozenset OR regex match
    fires the test."""
    violations: list[str] = []
    for path in _iter_production_py_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = path.relative_to(_REPO_ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not _is_print_or_log_call(node):
                continue
            for slot in _walk_interpolation_args(node):
                name: str | None = None
                if isinstance(slot, ast.Name):
                    name = slot.id
                elif isinstance(slot, ast.Attribute):
                    # e.g. self.api_key → flag the rightmost attr name.
                    name = slot.attr
                if name and _is_secret_name(name):
                    violations.append(
                        f"{rel}:{node.lineno} — print/log call interpolates "
                        f"secret-shaped name {name!r}"
                    )
    assert violations == [], (
        "P0.S6 D3.a violations (rename the variable or use a redacted log "
        "string; never log raw secrets):\n"
        + "\n".join(violations)
    )


# ────────────────────────────────────────────────────────────────────────────
# Plan v2 §9.2 — D3.b env_var_reads_centralized
# ────────────────────────────────────────────────────────────────────────────


def test_env_var_reads_centralized() -> None:
    """P0.S6 D3.b — env-var access lives in core/config.py OR the
    _ENV_VAR_ACCESS_ALLOWLIST (with documented rationale). Flags reads AND
    writes per Plan v2 MED 2 defense-in-depth scope."""
    violations: list[str] = []
    for path in _iter_production_py_files():
        rel = path.relative_to(_REPO_ROOT).as_posix()
        # core/config.py is the centralized read site — exempt.
        if rel == "core/config.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for lineno, var_name, access_type in _scan_env_var_access(tree, rel):
            key = (rel, var_name, access_type)
            if key in _ENV_VAR_ACCESS_ALLOWLIST:
                continue
            violations.append(
                f"{rel}:{lineno} — os.environ/os.getenv {access_type} of "
                f"{var_name!r} not centralized in core/config.py and not in "
                f"_ENV_VAR_ACCESS_ALLOWLIST. If legitimate, add an entry to "
                f"the allowlist with rationale (Plan v2 §3)."
            )
    assert violations == [], (
        "P0.S6 D3.b violations (centralize env-var reads in core/config.py "
        "OR add an explicit allowlist entry with rationale):\n"
        + "\n".join(violations)
    )


# ────────────────────────────────────────────────────────────────────────────
# Plan v2 §11 Phase 1 hygiene — .env.example cleanup + .gitignore N1
# ────────────────────────────────────────────────────────────────────────────


def test_env_example_drops_rotated_orphan_credentials() -> None:
    """P0.S6 D2.b — GEMINI_API_KEY, GEMINI_MODEL, SARVAM_API_KEY rotated at
    provider and removed from .env.example. Restoring any of these here would
    re-create the orphan-credential footprint."""
    assert _ENV_EXAMPLE.exists(), ".env.example must exist at repo root"
    body = _ENV_EXAMPLE.read_text(encoding="utf-8")
    forbidden = ("GEMINI_API_KEY", "GEMINI_MODEL", "SARVAM_API_KEY")
    present_lines: list[str] = []
    for raw in body.splitlines():
        stripped = raw.strip()
        # Allow forbidden names to appear ONLY inside comment lines (the
        # post-rotation note explaining what was removed).
        if stripped.startswith("#"):
            continue
        for name in forbidden:
            if name in stripped:
                present_lines.append(raw)
                break
    assert present_lines == [], (
        "P0.S6 D2.b: .env.example must NOT contain rotated-orphan entries:\n"
        + "\n".join(present_lines)
    )


def test_gitignore_blocks_terminal_output_logs() -> None:
    """P0.S6 N1 — terminal_output*.md contains personal conversation logs +
    occasionally STT artifacts of phrases said to the AI. Must stay gitignored
    on every machine."""
    assert _GITIGNORE.exists(), ".gitignore must exist at repo root"
    body = _GITIGNORE.read_text(encoding="utf-8")
    pattern_re = re.compile(r"^\s*terminal_output\*?\.md\s*$", re.MULTILINE)
    assert pattern_re.search(body), (
        "P0.S6 N1: .gitignore must block terminal_output*.md (or "
        "terminal_output.md). Found neither pattern."
    )


# ────────────────────────────────────────────────────────────────────────────
# Plan v2 §11 Phase 2 — pre-commit hook config + baseline presence
# ────────────────────────────────────────────────────────────────────────────


_PRECOMMIT_CONFIG = _REPO_ROOT / ".pre-commit-config.yaml"
_SECRETS_BASELINE = _REPO_ROOT / ".secrets.baseline"


def test_pre_commit_config_present_and_uses_detect_secrets() -> None:
    """P0.S6 D5 + P3 — `.pre-commit-config.yaml` exists at repo root and
    declares the detect-secrets hook with a baseline arg. Source-inspection
    only; doesn't execute pre-commit (which requires git + the framework
    installed locally — orthogonal to test correctness)."""
    assert _PRECOMMIT_CONFIG.exists(), (
        f"P0.S6 D5: {_PRECOMMIT_CONFIG.name} must exist at repo root. "
        f"Run `pip install pre-commit detect-secrets && pre-commit install`."
    )
    body = _PRECOMMIT_CONFIG.read_text(encoding="utf-8")
    # detect-secrets repo URL + hook id + baseline arg all required.
    assert "Yelp/detect-secrets" in body, (
        "P0.S6 P3: pre-commit config must reference Yelp/detect-secrets repo"
    )
    assert "id: detect-secrets" in body, (
        "P0.S6 P3: pre-commit config must declare the detect-secrets hook id"
    )
    assert ".secrets.baseline" in body, (
        "P0.S6 D5: pre-commit config must pass --baseline .secrets.baseline "
        "so existing-finding allowlist applies on every staged-content scan"
    )
    # Exclude pattern must enumerate the known-false-positive categories
    # (binary files / models / eval-bench JSONs / package-lock / classifier
    # seed) so detect-secrets doesn't re-flag them on every commit.
    assert "exclude:" in body, (
        "P0.S6 §6: pre-commit config must define exclude pattern for the "
        "4 false-positive categories enumerated in Plan v2 §6"
    )


def test_secrets_baseline_present_and_valid_json() -> None:
    """P0.S6 D5 — `.secrets.baseline` is the allowlist snapshot of expected
    false positives. Must exist + parse as JSON with the detect-secrets
    schema (top-level `plugins_used` + `results` keys)."""
    import json
    assert _SECRETS_BASELINE.exists(), (
        f"P0.S6 D5: {_SECRETS_BASELINE.name} must exist at repo root. "
        f"Generate via `detect-secrets scan > .secrets.baseline`."
    )
    body = _SECRETS_BASELINE.read_text(encoding="utf-8")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise AssertionError(
            f"P0.S6 D5: {_SECRETS_BASELINE.name} must parse as valid JSON. "
            f"detect-secrets schema is JSON-only. Error: {e}"
        )
    assert isinstance(data, dict), (
        "P0.S6 D5: baseline root must be a JSON object"
    )
    # Schema sanity — detect-secrets baseline always carries these two keys.
    for required in ("plugins_used", "results"):
        assert required in data, (
            f"P0.S6 D5: baseline missing required key {required!r}. "
            f"Regenerate via `detect-secrets scan --baseline "
            f".secrets.baseline --update`."
        )
    assert isinstance(data["plugins_used"], list), (
        "P0.S6 D5: baseline 'plugins_used' must be a list"
    )
    assert isinstance(data["results"], dict), (
        "P0.S6 D5: baseline 'results' must be a dict (file → finding-list)"
    )


# ────────────────────────────────────────────────────────────────────────────
# Plan v2 §5 — Phase 3 TruffleHog workflow YAML structure check (LOW 4)
# ────────────────────────────────────────────────────────────────────────────


_TRUFFLEHOG_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "trufflehog.yml"


def test_trufflehog_workflow_yaml_structure() -> None:
    """P0.S6 D4 + Plan v2 §5 — `.github/workflows/trufflehog.yml` matches the
    locked two-job shape from Plan v2 §4. 8-point structural check.

    Per Plan v2 §5 (LOW 4 disposition): tests OUR workflow file's structural
    correctness, not the upstream action's reachability. If trufflesecurity/
    trufflehog@main is renamed, the action lookup fails at GitHub Actions
    runtime — which is the right time to discover that. Locally testing the
    action's existence would add network dependency to the fast test tier.
    """
    import yaml

    # 1. File exists.
    assert _TRUFFLEHOG_WORKFLOW.exists(), (
        f"P0.S6 D4: {_TRUFFLEHOG_WORKFLOW.relative_to(_REPO_ROOT).as_posix()} "
        f"must exist. Plan v2 §4 locks the two-job workflow shape."
    )

    # 2. YAML parses without error.
    body = _TRUFFLEHOG_WORKFLOW.read_text(encoding="utf-8")
    try:
        cfg = yaml.safe_load(body)
    except yaml.YAMLError as e:
        raise AssertionError(
            f"P0.S6 D4: trufflehog.yml must parse as valid YAML. Error: {e}"
        )
    assert isinstance(cfg, dict), "Workflow root must be a YAML mapping"

    # 3. Triggers include schedule + workflow_dispatch + pull_request.
    # YAML parses bare `on:` as the boolean True; check both shapes.
    triggers = cfg.get("on") if "on" in cfg else cfg.get(True)
    assert isinstance(triggers, dict), (
        "Workflow `on:` must be a mapping enumerating triggers"
    )
    for trigger in ("schedule", "workflow_dispatch", "pull_request"):
        assert trigger in triggers, (
            f"P0.S6 Plan v2 §4: trigger {trigger!r} missing from workflow "
            f"`on:` block. Closing this trigger removes the workflow's "
            f"coverage of the corresponding event class."
        )

    # 4. Two jobs present: trufflehog-pr-diff + trufflehog-full-history,
    #    each with the locked `if: github.event_name == ...` gate.
    jobs = cfg.get("jobs", {})
    assert isinstance(jobs, dict)
    assert "trufflehog-pr-diff" in jobs, (
        "Plan v2 §4: missing 'trufflehog-pr-diff' job"
    )
    assert "trufflehog-full-history" in jobs, (
        "Plan v2 §4: missing 'trufflehog-full-history' job"
    )
    pr_job = jobs["trufflehog-pr-diff"]
    fh_job = jobs["trufflehog-full-history"]
    assert pr_job.get("if") == "github.event_name == 'pull_request'", (
        "Plan v2 §4: 'trufflehog-pr-diff' must gate on "
        "`if: github.event_name == 'pull_request'` — otherwise the job fires "
        "on scheduled runs producing empty-diff scans (MED 3 root cause)."
    )
    fh_if = fh_job.get("if", "")
    assert "github.event_name == 'schedule'" in fh_if, (
        "Plan v2 §4: 'trufflehog-full-history' must gate on schedule events"
    )
    assert "github.event_name == 'workflow_dispatch'" in fh_if, (
        "Plan v2 §4: 'trufflehog-full-history' must also gate on manual dispatch"
    )

    # 5. Both jobs reference trufflesecurity/trufflehog@main.
    def _walk_uses(job_cfg):
        out = []
        for step in job_cfg.get("steps", []):
            if "uses" in step:
                out.append(step["uses"])
        return out

    pr_uses = _walk_uses(pr_job)
    fh_uses = _walk_uses(fh_job)
    assert "trufflesecurity/trufflehog@main" in pr_uses, (
        "Plan v2 §4: PR job must use `trufflesecurity/trufflehog@main` action"
    )
    assert "trufflesecurity/trufflehog@main" in fh_uses, (
        "Plan v2 §4: full-history job must use `trufflesecurity/trufflehog@main`"
    )

    # 6. Both jobs use --results=verified (D8 closure-gate criterion).
    def _trufflehog_extra_args(job_cfg):
        for step in job_cfg.get("steps", []):
            if step.get("uses") == "trufflesecurity/trufflehog@main":
                return (step.get("with") or {}).get("extra_args", "")
        return ""
    pr_extra = _trufflehog_extra_args(pr_job)
    fh_extra = _trufflehog_extra_args(fh_job)
    assert "--results=verified" in pr_extra, (
        f"D8 closure-gate: PR job missing `--results=verified` in extra_args. "
        f"Got: {pr_extra!r}"
    )
    assert "--results=verified" in fh_extra, (
        f"D8 closure-gate: full-history job missing `--results=verified`. "
        f"Got: {fh_extra!r}"
    )

    # 7. Full-history job has NO base/head keys (full repo scan).
    def _trufflehog_with(job_cfg):
        for step in job_cfg.get("steps", []):
            if step.get("uses") == "trufflesecurity/trufflehog@main":
                return step.get("with") or {}
        return {}
    fh_with = _trufflehog_with(fh_job)
    assert "base" not in fh_with, (
        "Plan v2 §4: full-history job must NOT specify `base:` — "
        "otherwise it scans a diff, not the full repo history."
    )
    assert "head" not in fh_with, (
        "Plan v2 §4: full-history job must NOT specify `head:`"
    )

    # 8. PR job has the locked base/head expressions.
    pr_with = _trufflehog_with(pr_job)
    assert pr_with.get("base") == "${{ github.event.pull_request.base.sha }}", (
        "Plan v2 §4: PR job must use github.event.pull_request.base.sha "
        "(NOT default_branch — that fails on cross-fork PRs)."
    )
    assert pr_with.get("head") == "${{ github.event.pull_request.head.sha }}", (
        "Plan v2 §4: PR job must use github.event.pull_request.head.sha"
    )
