"""The sidebar values argus reports for a checkout."""
from __future__ import annotations

import unittest
from pathlib import Path

from argus.hg import Checkout, Counts
from argus.settings import Symbols
from argus.tokens import TOKEN_NAMES, tokens_for

SHARE = Checkout(Path("/x/myrepo-feature"), Path("/x/myrepo"), "default", None)


class Tokens(unittest.TestCase):
    def test_not_hg_clears_every_token(self) -> None:
        self.assertEqual(tokens_for(None, None, Symbols()), dict.fromkeys(TOKEN_NAMES))

    def test_clean_share_shows_names_and_no_counts(self) -> None:
        self.assertEqual(tokens_for(SHARE, Counts(0, 0, 0), Symbols()), {
            "hg_dirty": None, "hg_untracked": None, "hg_unpushed": None, "hg_branch": "default",
            "hg_bookmark": None, "hg_source": "myrepo"})

    def test_counts_use_star_question_mark_and_arrow(self) -> None:
        tokens = tokens_for(SHARE, Counts(89, 5, 2), Symbols())
        assert tokens is not None
        self.assertEqual((tokens["hg_dirty"], tokens["hg_untracked"], tokens["hg_unpushed"]),
                         ("*89", "?5", "↑2"))

    def test_a_plain_repo_has_no_source_and_shows_its_bookmark(self) -> None:
        plain_repo = Checkout(Path("/x/myrepo"), None, "stable", "mark")
        tokens = tokens_for(plain_repo, Counts(0, 0, 0), Symbols())
        assert tokens is not None
        self.assertEqual((tokens["hg_source"], tokens["hg_branch"], tokens["hg_bookmark"]),
                         (None, "stable", "mark"))

    def test_configured_symbols_are_used(self) -> None:
        tokens = tokens_for(SHARE, Counts(1, 2, 3), Symbols(dirty="M", untracked="U", unpushed="^"))
        assert tokens is not None
        self.assertEqual((tokens["hg_dirty"], tokens["hg_untracked"], tokens["hg_unpushed"]),
                         ("M1", "U2", "^3"))

    def test_failed_counts_leave_tokens_alone(self) -> None:
        self.assertIsNone(tokens_for(SHARE, None, Symbols()))


if __name__ == "__main__":
    unittest.main()
