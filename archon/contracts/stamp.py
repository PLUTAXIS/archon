"""Build stamps: every report records exactly what produced it."""
from __future__ import annotations

import subprocess
from importlib import metadata
from pathlib import Path


def _version() -> str:
    try:
        return metadata.version("archon")
    except metadata.PackageNotFoundError:
        return "0.0.0-dev"   # not installed — e.g. running from a bare checkout


def git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def stamp() -> dict:
    return {
        "archon_version": _version(),
        "git_sha": git_sha(),
        "dirty": _is_dirty(),
    }


def _is_dirty() -> bool:
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return bool(out)
    except Exception:
        return False
