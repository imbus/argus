"""What argus knows about an hg checkout: names from its .hg files, counts from hg itself."""
from __future__ import annotations

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

HG_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class Checkout:
    root: Path
    source: Path | None
    branch: str
    bookmark: str | None


@dataclass(frozen=True)
class Counts:
    uncommitted: int  # changes to tracked files: modified, added, removed, missing
    untracked: int
    unpushed: int


def find_checkout(directory: Path) -> Checkout | None:
    root = find_root(directory)
    if root is None:
        return None
    return Checkout(root, share_source(root), read_branch(root), read_active_bookmark(root))


def read_counts(root: Path) -> Counts | None:
    with ThreadPoolExecutor(max_workers=1) as pool:  # both hg calls at once
        pending_status = pool.submit(run_hg_guarded, root, "status", "-mardu")
        unpushed = run_hg_guarded(root, "log", "-r", "only(., public())", "-T", "x")
        status = pending_status.result()
    if status is None or unpushed is None:
        return None
    statuses = [line[:1] for line in status.splitlines() if line]
    untracked = statuses.count("?")
    return Counts(len(statuses) - untracked, untracked, len(unpushed))


def find_root(directory: Path) -> Path | None:
    try:
        start = directory.resolve()
        return next((d for d in (start, *start.parents) if (d / ".hg").is_dir()), None)
    except OSError:
        return None


def share_source(root: Path) -> Path | None:
    shared_store = read_text_guarded(root / ".hg" / "sharedpath")
    if shared_store is None or not shared_store.strip():
        return None
    # relative shares (`hg share --relative`) store the path relative to their own .hg
    return (root / ".hg" / shared_store.strip()).resolve().parent


def read_branch(root: Path) -> str:
    branch = read_text_guarded(root / ".hg" / "branch")
    return branch.strip() if branch and branch.strip() else "default"


def read_active_bookmark(root: Path) -> str | None:
    bookmark = read_text_guarded(root / ".hg" / "bookmarks.current")
    return bookmark.strip() if bookmark and bookmark.strip() else None


def read_text_guarded(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def run_hg_guarded(root: Path, *arguments: str) -> str | None:
    try:
        finished = subprocess.run(
            ["hg", "-R", str(root), *arguments], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=HG_TIMEOUT_SECONDS,
            env={**os.environ, "HGPLAIN": "1"}, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return finished.stdout if finished.returncode == 0 else None
