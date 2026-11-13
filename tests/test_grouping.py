"""Shares sit directly below their source repo's workspace, marked, sorted by folder."""
from __future__ import annotations

import random
import unittest
from collections.abc import Sequence
from pathlib import Path

from argus.grouping import Move, Rename, Workspace, desired_order, moves_to, renames, share_marks
from argus.settings import Symbols

MYREPO = Path("/r/myrepo")
OTHER = Path("/r/other")


def source(workspace_id: str, folder: Path, label: str | None = None) -> Workspace:
    return Workspace(workspace_id, label or folder.name, folder, None)


def share(workspace_id: str, name: str, of: Path = MYREPO, label: str | None = None) -> Workspace:
    folder = of.parent / name
    return Workspace(workspace_id, label if label is not None else folder.name, folder, of)


def plain(workspace_id: str) -> Workspace:
    return Workspace(workspace_id, workspace_id, None, None)


def ids(workspaces: Sequence[Workspace]) -> list[str]:
    return [w.workspace_id for w in workspaces]


def apply_moves(order: Sequence[str], moves: Sequence[Move]) -> list[str]:
    result = list(order)
    for move in moves:
        result.remove(move.workspace_id)
        result.insert(move.insert_index, move.workspace_id)
    return result


class Order(unittest.TestCase):
    def test_shares_move_directly_below_their_source_sorted_by_folder(self) -> None:
        sidebar = [share("b", "myrepo-b"), source("o", OTHER), source("m", MYREPO),
                   share("a", "myrepo-a")]
        self.assertEqual(desired_order(sidebar), ["o", "m", "a", "b"])

    def test_non_shares_keep_their_relative_order(self) -> None:
        sidebar = [plain("x"), share("a", "myrepo-a"), plain("y"), source("m", MYREPO),
                   plain("z")]
        order = desired_order(sidebar)
        self.assertEqual([i for i in order if i in {"x", "y", "m", "z"}], ["x", "y", "m", "z"])

    def test_share_without_open_source_stays_put(self) -> None:
        sidebar = [share("b", "myrepo-b"), plain("x"), share("a", "myrepo-a")]
        self.assertEqual(desired_order(sidebar), ["b", "x", "a"])

    def test_shares_follow_the_first_workspace_of_their_source(self) -> None:
        sidebar = [source("m1", MYREPO), plain("x"), source("m2", MYREPO), share("a", "myrepo-a")]
        self.assertEqual(desired_order(sidebar), ["m1", "a", "x", "m2"])

    def test_shares_of_different_sources_go_to_their_own_source(self) -> None:
        sidebar = [source("m", MYREPO), source("o", OTHER), share("oa", "other-a", of=OTHER),
                   share("ma", "myrepo-a")]
        self.assertEqual(desired_order(sidebar), ["m", "ma", "o", "oa"])

    def test_moves_are_only_issued_for_what_is_out_of_place(self) -> None:
        self.assertEqual(moves_to(["m", "x", "a"], ["m", "a", "x"]), [Move("a", 1)])


class Marks(unittest.TestCase):
    def test_shares_above_the_last_get_a_tee_and_the_last_a_corner(self) -> None:
        sidebar = [source("m", MYREPO), share("b", "myrepo-b"), share("a", "myrepo-a"),
                   share("c", "myrepo-c"), plain("x")]
        self.assertEqual(share_marks(sidebar, "├", "└"),
                         {"m": None, "a": "├", "b": "├", "c": "└", "x": None})

    def test_a_share_without_open_source_has_no_mark(self) -> None:
        self.assertEqual(share_marks([share("a", "myrepo-a"), plain("x")], "├", "└"),
                         {"a": None, "x": None})

    def test_a_label_the_user_chose_still_gets_its_mark(self) -> None:
        sidebar = [source("m", MYREPO), share("a", "myrepo-a", label="my feature")]
        self.assertEqual(share_marks(sidebar, "├", "└")["a"], "└")


class Labels(unittest.TestCase):
    def test_shares_are_named_after_their_folder_with_their_mark(self) -> None:
        sidebar = [source("m", MYREPO), share("b", "myrepo-b"), share("a", "myrepo-a")]
        self.assertEqual(renames(sidebar, Symbols()),
                         [Rename("b", "└ myrepo-b"), Rename("a", "├ myrepo-a")])

    def test_the_previous_last_share_gets_a_tee_when_one_is_added_below_it(self) -> None:
        sidebar = [source("m", MYREPO), share("a", "myrepo-a", label="└ myrepo-a"),
                   share("b", "myrepo-b")]
        self.assertEqual(renames(sidebar, Symbols()),
                         [Rename("a", "├ myrepo-a"), Rename("b", "└ myrepo-b")])

    def test_a_marked_share_gets_its_plain_name_back_when_its_source_closes(self) -> None:
        self.assertEqual(renames([share("a", "myrepo-a", label="├ myrepo-a")], Symbols()),
                         [Rename("a", "myrepo-a")])

    def test_configured_symbols_are_used_and_the_default_ones_still_recognised(self) -> None:
        sidebar = [source("m", MYREPO), share("a", "myrepo-a", label="└ myrepo-a")]
        self.assertEqual(renames(sidebar, Symbols(tree_middle="┊", tree_last="╰")),
                         [Rename("a", "╰ myrepo-a")])

    def test_a_label_the_user_chose_is_kept(self) -> None:
        sidebar = [source("m", MYREPO), share("a", "myrepo-a", label="my feature")]
        self.assertEqual(renames(sidebar, Symbols()), [])

    def test_a_marked_workspace_that_is_no_longer_a_share_loses_its_mark(self) -> None:
        moved_away = Workspace("a", "├ myrepo-a", Path("/r/elsewhere"), None)
        no_folder = Workspace("b", "└ myrepo-b", None, None)
        self.assertEqual(renames([moved_away, no_folder], Symbols()),
                         [Rename("a", "myrepo-a"), Rename("b", "myrepo-b")])

    def test_sources_and_plain_workspaces_are_never_renamed(self) -> None:
        self.assertEqual(renames([source("m", MYREPO, label="whatever"), plain("x")], Symbols()),
                         [])


def random_sidebar(generator: random.Random) -> list[Workspace]:
    sources = [MYREPO, OTHER]
    candidates: list[Workspace] = [plain(f"p{i}") for i in range(generator.randrange(4))]
    candidates += [source(f"s{i}", s) for i, s in enumerate(sources) if generator.random() < 0.6]
    for i in range(generator.randrange(6)):
        of = generator.choice(sources)
        label = generator.choice([None, None, "custom", f"├ {of.name}-{i}", f"└ {of.name}-{i}"])
        candidates.append(share(f"h{i}", f"{of.name}-{i}", of=of, label=label))
    generator.shuffle(candidates)
    return candidates


class Properties(unittest.TestCase):
    def test_applying_the_moves_gives_the_desired_order(self) -> None:
        generator = random.Random(11)
        for _ in range(300):
            sidebar = random_sidebar(generator)
            desired = desired_order(sidebar)
            self.assertEqual(apply_moves(ids(sidebar), moves_to(ids(sidebar), desired)), desired,
                             sidebar)

    def test_grouping_twice_moves_nothing(self) -> None:
        generator = random.Random(7)
        for _ in range(300):
            sidebar = random_sidebar(generator)
            by_id = {w.workspace_id: w for w in sidebar}
            grouped = [by_id[i] for i in desired_order(sidebar)]
            self.assertEqual(moves_to(ids(grouped), desired_order(grouped)), [], sidebar)
            self.assertEqual(share_marks(grouped, "├", "└"), share_marks(sidebar, "├", "└"))
            labels = {r.workspace_id: r.label for r in renames(grouped, Symbols())}
            relabelled = [Workspace(w.workspace_id, labels.get(w.workspace_id, w.label), w.folder,
                                    w.source) for w in grouped]
            self.assertEqual(renames(relabelled, Symbols()), [], sidebar)

    def test_every_workspace_appears_exactly_once(self) -> None:
        generator = random.Random(42)
        for _ in range(300):
            sidebar = random_sidebar(generator)
            self.assertEqual(sorted(desired_order(sidebar)), sorted(ids(sidebar)), sidebar)


if __name__ == "__main__":
    unittest.main()
