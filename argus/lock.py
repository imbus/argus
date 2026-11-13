"""One refresh at a time per herdr session; runs that find it busy queue their work for it."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import IO

from argus.refresh import Work

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


class RefreshLock:
    def __init__(self, state_dir: Path) -> None:
        self.lock_file = state_dir / "refresh.lock"
        self.queue_file = state_dir / "queued.jsonl"
        # per process: a run takes leftover work after releasing, while the next holder takes too
        self.taking_file = state_dir / f"queued.{os.getpid()}.taking"
        self.held: IO[bytes] | None = None

    def try_acquire(self) -> bool:
        # an OS lock: it goes away with its process, so a killed holder never blocks anyone
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        handle = self.lock_file.open("a+b")
        try:
            lock_without_waiting(handle)
        except OSError:
            handle.close()
            return False
        self.held = handle
        return True

    def release(self) -> None:
        if self.held is not None:
            self.held.close()  # closing drops the lock
            self.held = None

    def queue(self, work: Work) -> None:
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"regroup": work.regroup, "status_of_all": work.status_of_all,
                           "status_of": sorted(work.status_of)})
        with self.queue_file.open("a", encoding="utf-8") as queue:
            queue.write(line + "\n")

    def take_queued(self) -> Work | None:
        try:  # rename first, so runs queueing meanwhile start a fresh file
            self.queue_file.replace(self.taking_file)
        except FileNotFoundError:
            return None
        except PermissionError:  # Windows: another run has it open for appending; next pass
            return None
        lines = self.taking_file.read_text(encoding="utf-8", errors="replace").splitlines()
        self.taking_file.unlink()
        works = [work for work in map(work_from_json_guarded, lines) if work is not None]
        merged: Work | None = None
        for work in works:
            merged = work if merged is None else merged.merged(work)
        return merged


def lock_without_waiting(handle: IO[bytes]) -> None:
    if sys.platform == "win32":
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def work_from_json_guarded(line: str) -> Work | None:
    try:  # a run killed mid-append leaves half a line
        fields = json.loads(line)
        return Work(bool(fields["regroup"]), bool(fields["status_of_all"]),
                    frozenset(str(i) for i in fields["status_of"]))
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
