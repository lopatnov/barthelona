#!/usr/bin/env python3
"""WSL agent — runs inside the WSL Ubuntu distro, speaks JSON lines.

Deployed to ``~/.local/share/barthelona/agent.py`` by the worker before
use.  The worker verifies its sha256 before starting it.

Protocol (architecture §12, D-043):
- First output line: ``{"hello": {"protocol": 2, "cache_root": "/abs/path"}}``
- Input  (stdin):  one JSON object per line
  ``{"id": int, "cmd": [...], "cwd": str|null, "env": {str: str}|null,
    "stdin": base64|null, "timeout": float}``
- Output (stdout): one JSON object per line, echoing the request id
  ``{"id": int, "returncode": int, "stdout": base64, "stderr": base64, "elapsed": float}``
  A refused request carries ``"rejected": true`` and a plain-text ``stderr``.
- Requests run concurrently in a bounded pool, so replies may arrive out of order.

Allowlist (only these command prefixes are permitted):
  - ``docker exec bart-tc …``
  - ``docker run <bart-run*> …``  — sandbox flags are FIXED by this agent;
    the caller supplies only the image name and command, never docker options.
  - ``docker inspect --format … <bart-tc|bart-run*>``  — image name is
    restricted to the toolchain and runner images.
  - ``tar …``
  - ``sha256sum …``

All paths in ``cwd`` and in known path-carrying argv positions must be
under ``~/.cache/barthelona/``.  Generated binaries NEVER run outside the
sandbox container.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath

#: Bumped when the wire format changes; the host refuses a mismatched agent (D-043).
PROTOCOL_VERSION = 2
_MAX_CONCURRENCY = 4
_CACHE_ROOT = str(Path("~/.cache/barthelona").expanduser())
_TC_CONTAINER = "bart-tc"
_RUN_IMAGE_PREFIX = "bart-run"

# Mandatory sandbox flags applied to every docker run (architecture §12, invariant 2).
# The caller must NOT supply any docker flags; it provides only the image and command.
_SANDBOX_FLAGS: tuple[str, ...] = (
    "--network",
    "none",
    "--read-only",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges",
    "--user",
    "65534:65534",
    "--memory",
    "256m",
    "--memory-swap",
    "256m",
    "--pids-limit",
    "64",
    "--cpus",
    "1",
    "--tmpfs",
    "/tmp:size=16m",  # noqa: S108 -- docker --tmpfs flag, not a host path
    "--rm",
)

_ALLOWED_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("docker", "exec", _TC_CONTAINER),
    ("docker", "run"),
    ("docker", "inspect"),
    ("tar",),
    ("sha256sum",),
)


def _is_allowed(argv: list[str]) -> bool:
    """Return True only when argv matches the agent allow-list prefix.

    For ``docker run``, ``_build_docker_run_argv`` performs the full validation
    and reconstruction; this function checks only the surface match.
    """
    for prefix in _ALLOWED_PREFIXES:
        if tuple(argv[: len(prefix)]) == prefix:
            # For docker run: caller must pass [docker, run, <image>, *cmd] with no flags.
            # Full validation happens in _build_docker_run_argv.
            return not (
                prefix == ("docker", "run") and (len(argv) < 3 or not argv[2].startswith(_RUN_IMAGE_PREFIX))
            )
    return False


def _build_docker_run_argv(argv: list[str]) -> list[str] | None:
    """Reconstruct a docker run command with fixed sandbox flags.

    The caller must supply exactly ``["docker", "run", "<image>", *cmd_args]``
    with no docker options; the agent inserts the full sandbox flag set
    (architecture §12, invariant 2).

    Returns ``None`` when the argv is invalid (caller-supplied flags, wrong
    image prefix, or missing image).
    """
    if len(argv) < 3:
        return None
    image = argv[2]
    if image.startswith("-"):
        # Caller passed a docker flag — reject; sandbox flags are agent-only.
        return None
    if not image.startswith(_RUN_IMAGE_PREFIX):
        return None
    cmd_args = argv[3:]
    return ["docker", "run", *_SANDBOX_FLAGS, image, *cmd_args]


def _validate_docker_inspect_argv(argv: list[str]) -> bool:
    """Check that docker inspect targets exactly one allowed image.

    Only ``bart-tc`` (the toolchain container) and images whose name starts
    with ``bart-run`` (the runner image prefix) may be inspected; exactly one
    target is permitted to prevent multi-target calls from enumerating
    arbitrary images alongside an allowed name.

    ``--format VALUE`` and ``-f VALUE`` are each two tokens; the value is
    consumed so it is not mistaken for an image target.
    """
    args = argv[2:]
    targets: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--format", "-f"):
            i += 2  # skip flag and its value
        elif a.startswith("-"):
            i += 1
        else:
            targets.append(a)
            i += 1
    return len(targets) == 1 and (targets[0] == _TC_CONTAINER or targets[0].startswith(_RUN_IMAGE_PREFIX))


def _is_safe_path(path: str) -> bool:
    """Return True when *path* is under the cache root after full resolution."""
    try:
        resolved = PurePosixPath(Path(path).expanduser().resolve())
        return str(resolved).startswith(_CACHE_ROOT)
    except Exception:  # any resolution failure means the path is unsafe
        return False


def _validate_tar_paths(argv: list[str]) -> bool:
    """Check that the -C destination and absolute path arguments in a tar command are safe.

    Addresses the partial path-fence gap: cwd is checked in _handle(), but
    path-bearing flags embedded in argv (``-C dir``, absolute file arguments)
    must also be fenced to ``~/.cache/barthelona/``.

    Relative paths (e.g. ``.``, ``src/``) are allowed because they are
    resolved against cwd, which is already validated separately.
    """
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "-C":
            if i + 1 >= len(argv):
                return False
            if not _is_safe_path(argv[i + 1]):
                return False
            i += 2
            continue
        # Only validate absolute or home-relative paths; relative ones are
        # resolved against cwd (checked by _handle()) and are safe.
        if not arg.startswith("-") and arg != "-" and arg.startswith(("/", "~")) and not _is_safe_path(arg):
            return False
        i += 1
    return True


def _validate_sha256sum_argv(argv: list[str]) -> bool:
    """Check that sha256sum file arguments are inside the cache root.

    Relative paths are resolved against cwd, which is checked separately in
    ``_handle``; only absolute and home-relative paths are fenced here.
    Flags (anything starting with ``-``) and the stdin sentinel ``-`` are
    skipped.
    """
    for arg in argv[1:]:  # argv[0] is "sha256sum"
        if arg.startswith("-"):
            continue
        if arg.startswith(("/", "~")) and not _is_safe_path(arg):
            return False
    return True


def _validate_request(argv: list[str], cwd_raw: object) -> str | None:
    """Return the rejection message for *argv* / *cwd_raw*, or ``None`` when allowed."""
    if not _is_allowed(argv):
        return f"command not on allow-list: {argv[0]!r}"
    if argv[:2] == ["docker", "run"] and _build_docker_run_argv(argv) is None:
        return "invalid docker run: supply only image and command; docker flags are injected by the agent"
    if argv[0] == "tar" and not _validate_tar_paths(argv[1:]):
        return "tar path argument outside cache root"
    if argv[:2] == ["docker", "inspect"] and not _validate_docker_inspect_argv(argv):
        return "docker inspect only allowed for bart-tc and bart-run* images"
    if argv[0] == "sha256sum" and not _validate_sha256sum_argv(argv):
        return "sha256sum path argument outside cache root"
    if cwd_raw and not _is_safe_path(str(cwd_raw)):
        return f"cwd outside cache root: {str(cwd_raw)!r}"
    return None


def _rejection(message: str) -> dict[str, object]:
    """A request the agent refused to run; ``stderr`` is plain text, not base64."""
    return {"returncode": 1, "stdout": "", "stderr": message, "elapsed": 0.0, "rejected": True}


def _handle(request: dict[str, object]) -> dict[str, object]:
    cmd_raw = request.get("cmd")
    argv: list[str] = [str(a) for a in (cmd_raw if isinstance(cmd_raw, list) else [])]
    if not argv:
        return _rejection("empty cmd")

    error = _validate_request(argv, request.get("cwd"))
    if error is not None:
        return _rejection(error)
    if argv[:2] == ["docker", "run"]:
        # Reconstruct docker run with hardcoded sandbox flags; fail closed if the rebuild is refused.
        rebuilt = _build_docker_run_argv(argv)
        if rebuilt is None:
            return _rejection("invalid docker run")
        argv = rebuilt

    cwd_raw = request.get("cwd")
    cwd: str | None = str(cwd_raw) if cwd_raw else None

    # For tar extract operations, create the destination directory first.
    if argv[0] == "tar":
        try:
            c_idx = argv.index("-C")
            extract_dir = Path(argv[c_idx + 1]).expanduser()
            if str(extract_dir).startswith(_CACHE_ROOT):
                extract_dir.mkdir(parents=True, exist_ok=True)
        except (ValueError, IndexError, OSError):
            pass

    env: dict[str, str] | None = None
    raw_env = request.get("env")
    if isinstance(raw_env, dict):
        env = {str(k): str(v) for k, v in raw_env.items()}

    stdin_b64 = request.get("stdin")
    stdin_bytes = base64.b64decode(str(stdin_b64)) if stdin_b64 else None
    timeout_raw = request.get("timeout")
    timeout = float(timeout_raw if isinstance(timeout_raw, (int, float)) else 30.0)

    t0 = time.monotonic()
    try:
        proc = subprocess.run(  # noqa: S603  -- argv is allow-list validated; shell=False (default)
            argv,
            input=stdin_bytes,
            capture_output=True,
            cwd=cwd,
            env=env,
            timeout=timeout,
        )
        elapsed = time.monotonic() - t0
        return {
            "returncode": proc.returncode,
            "stdout": base64.b64encode(proc.stdout).decode(),
            "stderr": base64.b64encode(proc.stderr).decode(),
            "elapsed": elapsed,
        }
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - t0
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": base64.b64encode(f"timeout after {timeout}s".encode()).decode(),
            "elapsed": elapsed,
        }
    except Exception as exc:  # all unhandled process errors reported as returncode -1
        elapsed = time.monotonic() - t0
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": base64.b64encode(str(exc).encode()).decode(),
            "elapsed": elapsed,
        }


def _reply(request_id: object, response: dict[str, object], lock: threading.Lock) -> None:
    out = {"id": request_id, **response}
    data = json.dumps(out, separators=(",", ":")).encode() + b"\n"
    with lock:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()


def _serve_line(line: bytes, lock: threading.Lock) -> None:
    request_id: object = None
    try:
        request = json.loads(line)
    except json.JSONDecodeError as exc:
        response = _rejection(f"bad JSON: {exc}")
    else:
        if isinstance(request, dict):
            request_id = request.get("id")
            response = _handle(request)
        else:
            response = _rejection("request must be a JSON object")
    _reply(request_id, response, lock)


def main() -> None:
    """Announce the protocol, then serve requests concurrently until stdin closes."""
    lock = threading.Lock()
    hello = {"hello": {"protocol": PROTOCOL_VERSION, "cache_root": _CACHE_ROOT}}
    with lock:
        sys.stdout.buffer.write(json.dumps(hello, separators=(",", ":")).encode() + b"\n")
        sys.stdout.buffer.flush()
    with ThreadPoolExecutor(max_workers=_MAX_CONCURRENCY) as pool:
        for raw_line in sys.stdin.buffer:
            line = raw_line.strip()
            if line:
                pool.submit(_serve_line, line, lock)


if __name__ == "__main__":
    main()
