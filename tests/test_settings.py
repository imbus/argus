"""Symbols are configurable in the plugin's config.toml; anything unusable falls back."""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from argus.settings import Symbols, load_symbols


class Settings(unittest.TestCase):
    def test_without_a_config_the_defaults_apply(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_symbols(Path(directory)), Symbols())
        self.assertEqual(Symbols(), Symbols("*", "?", "↑", "├", "└"))

    def test_configured_symbols_replace_only_what_they_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "config.toml").write_text(
                '[symbols]\ntree_middle = "·"\ntree_last = "╰"\n', encoding="utf-8")
            self.assertEqual(load_symbols(Path(directory)),
                             Symbols(tree_middle="·", tree_last="╰"))

    def test_a_broken_config_falls_back_and_says_why(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "config.toml").write_text("[symbols\n", encoding="utf-8")
            errors = io.StringIO()
            with redirect_stderr(errors):
                self.assertEqual(load_symbols(Path(directory)), Symbols())
            self.assertIn("config.toml", errors.getvalue())

    def test_unknown_or_non_text_settings_are_ignored_with_a_note(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "config.toml").write_text(
                '[symbols]\ndirty = 3\nsparkle = "x"\nunpushed = "^"\n', encoding="utf-8")
            errors = io.StringIO()
            with redirect_stderr(errors):
                self.assertEqual(load_symbols(Path(directory)), Symbols(unpushed="^"))
            self.assertIn("dirty", errors.getvalue())
            self.assertIn("sparkle", errors.getvalue())

    def test_no_config_directory_means_defaults(self) -> None:
        self.assertEqual(load_symbols(None), Symbols())


if __name__ == "__main__":
    unittest.main()
