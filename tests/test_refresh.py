"""Which herdr events lead to which work, and a refresh that survives one bad workspace."""
from __future__ import annotations

import io
import unittest
from collections.abc import Mapping
from contextlib import redirect_stderr
from pathlib import Path
from typing import override
from unittest import mock

from argus.grouping import Move, Rename
from argus.herdr import Herdr, HerdrError, Pane, WorkspaceInfo
from argus.hg import Checkout, Counts
from argus.refresh import Work, refresh, work_for_event
from argus.settings import Symbols

CONTEXT = {"workspace_id": "w7", "focused_pane_cwd": "/r/myrepo"}
NOTHING = Work(regroup=False, status_of_all=False, status_of=frozenset())
REGROUP = Work(regroup=True, status_of_all=False, status_of=frozenset())
STATUS_OF_ALL = Work(regroup=False, status_of_all=True, status_of=frozenset())


def agent_event(status: str) -> dict[str, object]:
    return {"event": "pane_agent_status_changed",
            "data": {"workspace_id": "w3", "pane_id": "w3:p1", "agent_status": status}}


class Events(unittest.TestCase):
    def test_startup_regroups_and_refreshes_everything(self) -> None:
        self.assertEqual(work_for_event(None, {}, {}),
                         Work(regroup=True, status_of_all=True, status_of=frozenset()))

    def test_created_workspace_regroups_and_refreshes_itself(self) -> None:
        self.assertEqual(work_for_event("workspace.created", {}, CONTEXT),
                         Work(regroup=True, status_of_all=False, status_of=frozenset({"w7"})))

    def test_closed_workspace_only_regroups(self) -> None:
        self.assertEqual(work_for_event("workspace.closed", {}, CONTEXT),
                         Work(regroup=True, status_of_all=False, status_of=frozenset()))

    def test_focus_refreshes_that_workspace(self) -> None:
        self.assertEqual(work_for_event("workspace.focused", {}, CONTEXT),
                         Work(regroup=False, status_of_all=False, status_of=frozenset({"w7"})))

    def test_agent_settling_refreshes_its_workspace(self) -> None:
        for status in ("idle", "done", "blocked"):
            self.assertEqual(work_for_event("pane.agent_status_changed", agent_event(status), {}),
                             Work(regroup=False, status_of_all=False, status_of=frozenset({"w3"})))

    def test_agent_starting_work_does_nothing(self) -> None:
        self.assertEqual(work_for_event("pane.agent_status_changed", agent_event("working"), {}),
                         NOTHING)

    def test_unknown_events_and_missing_ids_do_nothing(self) -> None:
        self.assertEqual(work_for_event("workspace.renamed", {}, CONTEXT), NOTHING)
        self.assertEqual(work_for_event("workspace.focused", {}, {}), NOTHING)

    def test_merged_work_covers_both(self) -> None:
        merged = Work(True, False, frozenset({"a"})).merged(Work(False, True, frozenset({"b"})))
        self.assertEqual(merged, Work(True, True, frozenset({"a", "b"})))


class RecordingHerdr(Herdr):
    def __init__(self, panes: list[Pane], fail_report_for: str = "") -> None:
        super().__init__("/unused")
        self.listed_panes = panes
        self.fail_report_for = fail_report_for
        self.reported: dict[str, dict[str, str | None]] = {}
        self.moved: list[Move] = []
        self.renamed: list[Rename] = []
        self.active_tabs: dict[str, str] = {}

    @override
    def workspaces(self) -> list[WorkspaceInfo]:
        first_pane: dict[str, Pane] = {}
        for pane in self.listed_panes:
            first_pane.setdefault(pane.workspace_id, pane)
        return [WorkspaceInfo(p.workspace_id, p.cwd.name,
                              self.active_tabs.get(p.workspace_id, p.tab_id))
                for p in first_pane.values()]

    @override
    def panes(self) -> list[Pane]:
        return self.listed_panes

    @override
    def report(self, workspace_id: str, tokens: Mapping[str, str | None]) -> None:
        if workspace_id == self.fail_report_for:
            raise HerdrError("boom")
        if workspace_id == "explodes":
            raise ValueError("unexpected")
        self.reported[workspace_id] = {**self.reported.get(workspace_id, {}), **tokens}

    @override
    def move(self, move: Move) -> None:
        self.moved.append(move)

    @override
    def rename(self, rename: Rename) -> None:
        self.renamed.append(rename)


def fake_checkout(directory: Path) -> Checkout | None:
    source = Path("/r/myrepo") if directory.name.startswith("myrepo-") else None
    return Checkout(directory, source, "default", None)


def one_uncommitted_file(_root: Path) -> Counts:
    return Counts(1, 0, 0)


def refresh_with_default_symbols(herdr: Herdr, work: Work) -> None:
    refresh(herdr, work, Symbols())


class Refreshing(unittest.TestCase):
    @override
    def setUp(self) -> None:
        for target, fake in (("argus.refresh.find_checkout", fake_checkout),
                             ("argus.refresh.read_counts", one_uncommitted_file)):
            patcher = mock.patch(target, side_effect=fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_one_failing_workspace_does_not_stop_the_rest(self) -> None:
        herdr = RecordingHerdr([Pane("w1", "w1:t1", Path("/r/a"), True),
                                Pane("w2", "w2:t1", Path("/r/b"), True)], fail_report_for="w1")
        with redirect_stderr(io.StringIO()):
            refresh_with_default_symbols(herdr, STATUS_OF_ALL)
        self.assertEqual(set(herdr.reported), {"w2"})
        self.assertEqual(herdr.reported["w2"]["hg_dirty"], "*1")

    def test_regroup_moves_and_marks_shares_under_their_source(self) -> None:
        herdr = RecordingHerdr([Pane("w1", "w1:t1", Path("/r/myrepo-a"), True),
                                Pane("w2", "w2:t1", Path("/r/myrepo"), True)])
        refresh_with_default_symbols(herdr, REGROUP)
        self.assertEqual(herdr.renamed, [Rename("w1", "└ myrepo-a")])
        self.assertEqual(herdr.moved, [Move("w2", 0)])
        self.assertEqual(herdr.reported, {})

    def test_the_active_tab_decides_the_folder(self) -> None:
        # herdr marks one pane focused in the whole session, so each workspace's active tab counts
        herdr = RecordingHerdr([Pane("w1", "w1:t1", Path("/r/myrepo"), False),
                                Pane("w1", "w1:t2", Path("/r/myrepo-a"), False)])
        herdr.active_tabs = {"w1": "w1:t2"}
        refresh_with_default_symbols(herdr, Work(False, False, frozenset({"w1"})))
        self.assertEqual(herdr.reported["w1"]["hg_source"], "myrepo")

    def test_a_status_update_only_looks_up_its_own_checkout(self) -> None:
        herdr = RecordingHerdr([Pane("w1", "w1:t1", Path("/r/a"), True),
                                Pane("w2", "w2:t1", Path("/r/b"), True)])
        with mock.patch("argus.refresh.find_checkout", side_effect=fake_checkout) as lookup:
            refresh_with_default_symbols(herdr, Work(False, False, frozenset({"w2"})))
        self.assertEqual([c.args[0] for c in lookup.call_args_list], [Path("/r/b")])

    def test_unexpected_errors_are_reported_and_the_rest_go_on(self) -> None:
        herdr = RecordingHerdr([Pane("explodes", "explodes:t1", Path("/r/a"), True),
                                Pane("w2", "w2:t1", Path("/r/b"), True)])
        errors = io.StringIO()
        with redirect_stderr(errors):
            refresh_with_default_symbols(herdr, STATUS_OF_ALL)
        self.assertEqual(set(herdr.reported), {"w2"})
        self.assertIn("unexpected", errors.getvalue())

if __name__ == "__main__":
    unittest.main()
