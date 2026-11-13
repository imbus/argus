"""One refresh at a time; work arriving meanwhile is queued for the running one."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import override
from unittest import mock

from argus.lock import RefreshLock
from argus.refresh import Work


class Locking(unittest.TestCase):
    state_dir: Path

    @override
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.state_dir = Path(directory.name) / "state"

    def test_second_acquire_fails_while_held(self) -> None:
        first, second = RefreshLock(self.state_dir), RefreshLock(self.state_dir)
        self.assertTrue(first.try_acquire())
        self.assertFalse(second.try_acquire())
        first.release()
        self.assertTrue(second.try_acquire())
        second.release()

    def test_a_killed_holder_leaves_no_lock_behind(self) -> None:
        holder = ("import sys; from pathlib import Path; from argus.lock import RefreshLock; "
                  "assert RefreshLock(Path(sys.argv[1])).try_acquire(); sys.exit(0)")
        subprocess.run([sys.executable, "-c", holder, str(self.state_dir)], check=True)
        after = RefreshLock(self.state_dir)
        self.assertTrue(after.try_acquire())
        after.release()

    def test_a_broken_queue_line_is_skipped(self) -> None:
        holder = RefreshLock(self.state_dir)
        holder.queue(Work(regroup=True, status_of_all=False, status_of=frozenset()))
        with (self.state_dir / "queued.jsonl").open("a", encoding="utf-8") as queue:
            queue.write('{"regroup": tr\n')
        self.assertEqual(holder.take_queued(), Work(True, False, frozenset()))

    def test_a_queue_another_process_has_open_is_left_for_later(self) -> None:
        holder = RefreshLock(self.state_dir)
        holder.queue(Work(regroup=True, status_of_all=False, status_of=frozenset()))
        with mock.patch.object(Path, "replace", side_effect=PermissionError("in use")):
            self.assertIsNone(holder.take_queued())
        self.assertEqual(holder.take_queued(), Work(True, False, frozenset()))

    def test_queued_work_is_merged_and_taken_once(self) -> None:
        holder, waiting = RefreshLock(self.state_dir), RefreshLock(self.state_dir)
        self.assertTrue(holder.try_acquire())
        self.addCleanup(holder.release)
        waiting.queue(Work(regroup=True, status_of_all=False, status_of=frozenset({"a"})))
        waiting.queue(Work(regroup=False, status_of_all=False, status_of=frozenset({"b"})))
        self.assertEqual(holder.take_queued(),
                         Work(regroup=True, status_of_all=False, status_of=frozenset({"a", "b"})))
        self.assertIsNone(holder.take_queued())


if __name__ == "__main__":
    unittest.main()
