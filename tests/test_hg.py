"""Reading a checkout's facts from its .hg files, and its counts from hg itself."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import override

from argus.hg import Checkout, Counts, find_checkout, read_counts

HG_ENV = {**os.environ, "HGPLAIN": "1", "HGUSER": "test <test@example.com>"}


def hg(repository: Path, *arguments: str) -> None:
    subprocess.run(["hg", "--cwd", str(repository), *arguments], env=HG_ENV, check=True,
                   capture_output=True)


@unittest.skipUnless(shutil.which("hg"), "needs hg on PATH")
class HgCheckout(unittest.TestCase):
    parent: Path
    repository: Path

    @override
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name).resolve()
        self.repository = self.parent / "myrepo"
        subprocess.run(["hg", "init", str(self.repository)], env=HG_ENV, check=True)
        (self.repository / "file.txt").write_text("one\n")
        hg(self.repository, "commit", "-A", "-m", "first")

    def share(self, name: str, *options: str) -> Path:
        hg(self.parent, "--config", "extensions.share=", "share", *options, "myrepo", name)
        return self.parent / name

    def test_a_folder_inside_a_repo_finds_its_root(self) -> None:
        inner = self.repository / "sub" / "dir"
        inner.mkdir(parents=True)
        checkout = find_checkout(inner)
        self.assertIsNotNone(checkout)
        assert checkout is not None
        self.assertEqual(checkout.root, self.repository)

    def test_a_folder_outside_any_repo_is_not_hg(self) -> None:
        outside = self.parent / "elsewhere"
        outside.mkdir()
        self.assertIsNone(find_checkout(outside))

    def test_missing_directory_is_not_hg(self) -> None:
        self.assertIsNone(find_checkout(self.parent / "gone"))

    def test_a_plain_repo_has_no_source(self) -> None:
        self.assertEqual(find_checkout(self.repository),
                         Checkout(self.repository, None, "default", None))

    def test_a_share_knows_its_source(self) -> None:
        share = self.share("myrepo-feature")
        checkout = find_checkout(share)
        assert checkout is not None
        self.assertEqual(checkout.source, self.repository)

    def test_a_relative_share_knows_its_source(self) -> None:
        share = self.share("myrepo-relative", "--relative")
        checkout = find_checkout(share)
        assert checkout is not None
        self.assertEqual(checkout.source, self.repository)

    def test_branch_defaults_to_default(self) -> None:
        checkout = find_checkout(self.repository)
        assert checkout is not None
        self.assertEqual(checkout.branch, "default")

    def test_named_branch_is_read(self) -> None:
        hg(self.repository, "branch", "feature-x")
        hg(self.repository, "commit", "-m", "on feature-x")
        checkout = find_checkout(self.repository)
        assert checkout is not None
        self.assertEqual(checkout.branch, "feature-x")

    def test_active_bookmark_is_read(self) -> None:
        hg(self.repository, "bookmark", "my-mark")
        checkout = find_checkout(self.repository)
        assert checkout is not None
        self.assertEqual(checkout.bookmark, "my-mark")

    def test_no_active_bookmark_is_none(self) -> None:
        hg(self.repository, "bookmark", "my-mark")
        hg(self.repository, "bookmark", "--inactive")
        checkout = find_checkout(self.repository)
        assert checkout is not None
        self.assertIsNone(checkout.bookmark)

    def test_clean_repo_has_nothing_to_report(self) -> None:
        hg(self.repository, "phase", "--public", ".")
        self.assertEqual(read_counts(self.repository), Counts(0, 0, 0))

    def test_changes_to_tracked_files_count_as_uncommitted(self) -> None:
        (self.repository / "file.txt").write_text("two\n")
        (self.repository / "added.txt").write_text("added\n")
        hg(self.repository, "add", "added.txt")
        counts = read_counts(self.repository)
        assert counts is not None
        self.assertEqual((counts.uncommitted, counts.untracked), (2, 0))

    def test_untracked_files_are_counted_separately(self) -> None:
        (self.repository / "new.txt").write_text("new\n")
        (self.repository / "other.txt").write_text("other\n")
        counts = read_counts(self.repository)
        assert counts is not None
        self.assertEqual((counts.uncommitted, counts.untracked), (0, 2))

    def test_draft_commits_count_as_unpushed(self) -> None:
        for content in ("two\n", "three\n"):
            (self.repository / "file.txt").write_text(content)
            hg(self.repository, "commit", "-m", content.strip())
        hg(self.repository, "phase", "--public", "-r", "0")
        counts = read_counts(self.repository)
        assert counts is not None
        self.assertEqual(counts.unpushed, 2)
        hg(self.repository, "phase", "--public", ".")
        self.assertEqual(read_counts(self.repository), Counts(0, 0, 0))

    def test_failing_hg_gives_no_counts(self) -> None:
        outside = self.parent / "elsewhere"
        outside.mkdir()
        self.assertIsNone(read_counts(outside))


if __name__ == "__main__":
    unittest.main()
