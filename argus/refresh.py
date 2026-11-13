"""What a herdr event asks argus to do, and doing it: regroup the sidebar, report hg status."""
from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from argus.grouping import Workspace, desired_order, moves_to, renames
from argus.herdr import Herdr, HerdrError, Pane, WorkspaceInfo
from argus.hg import Checkout, find_checkout, read_counts
from argus.settings import Symbols
from argus.tokens import tokens_for

SETTLED_AGENT_STATES = frozenset({"idle", "done", "blocked"})
PARALLEL_HG_CALLS = 4


@dataclass(frozen=True)
class Work:
    regroup: bool
    status_of_all: bool
    status_of: frozenset[str]

    def merged(self, other: Work) -> Work:
        return Work(self.regroup or other.regroup, self.status_of_all or other.status_of_all,
                    self.status_of | other.status_of)

    def is_empty(self) -> bool:
        return not (self.regroup or self.status_of_all or self.status_of)


NO_WORK = Work(regroup=False, status_of_all=False, status_of=frozenset())


def work_for_event(event: str | None, event_json: Mapping[str, Any],
                   context_json: Mapping[str, Any]) -> Work:
    if event == "pane.agent_status_changed":
        return work_when_agent_settles(event_json)
    context_workspace = ids_present(context_json.get("workspace_id"))
    match event:
        case None:  # [[startup]] runs without an event
            return Work(regroup=True, status_of_all=True, status_of=frozenset())
        case "workspace.created":
            return Work(regroup=True, status_of_all=False, status_of=context_workspace)
        case "workspace.closed":
            return Work(regroup=True, status_of_all=False, status_of=frozenset())
        case "workspace.focused":  # herdr has no event for a changed folder; catch it here
            return Work(regroup=True, status_of_all=False, status_of=context_workspace)
        case _:
            return NO_WORK


def work_when_agent_settles(event_json: Mapping[str, Any]) -> Work:
    data: Mapping[str, Any] = event_json.get("data") or {}
    if data.get("agent_status") not in SETTLED_AGENT_STATES:
        return NO_WORK
    return Work(regroup=False, status_of_all=False,
                status_of=ids_present(data.get("workspace_id")))


def refresh(herdr: Herdr, work: Work, symbols: Symbols, labels_file: Path) -> None:
    if work.is_empty():
        return
    workspaces = herdr.workspaces()
    folders = folder_per_workspace(herdr.panes(), workspaces)
    all_ids = [w.workspace_id for w in workspaces]
    targets = all_ids if work.status_of_all else [i for i in all_ids if i in work.status_of]
    needed = all_ids if work.regroup else targets  # regrouping needs every checkout
    checkouts = {i: find_checkout(folders[i]) for i in needed if i in folders}
    if work.regroup:
        sidebar = [as_workspace(w.workspace_id, w.label, checkouts.get(w.workspace_id),
                                folders.get(w.workspace_id)) for w in workspaces]
        regroup_guarded(herdr, sidebar, symbols, labels_file)
    with ThreadPoolExecutor(max_workers=PARALLEL_HG_CALLS) as pool:
        for workspace_id in targets:
            pool.submit(report_status_guarded, herdr, workspace_id, checkouts.get(workspace_id),
                        symbols)


def folder_per_workspace(panes: Sequence[Pane],
                         workspaces: Sequence[WorkspaceInfo]) -> dict[str, Path]:
    # herdr marks one pane focused in the whole session: the active tab is what each workspace shows
    active_tabs = {w.workspace_id: w.active_tab_id for w in workspaces}
    preference = sorted(panes, key=lambda p: (p.tab_id != active_tabs.get(p.workspace_id),
                                              not p.focused))
    folders: dict[str, Path] = {}
    for pane in preference:
        folders.setdefault(pane.workspace_id, pane.cwd)
    return folders


def regroup_guarded(herdr: Herdr, workspaces: Sequence[Workspace], symbols: Symbols,
                    labels_file: Path) -> None:
    set_by_argus = read_labels_guarded(labels_file)
    try:
        for rename in renames(workspaces, symbols, set_by_argus):
            herdr.rename(rename)
            set_by_argus[rename.workspace_id] = rename.label
        # one failed move shifts every later index, so stop at the first failure
        for move in moves_to([w.workspace_id for w in workspaces], desired_order(workspaces)):
            herdr.move(move)
    except HerdrError as error:
        print(f"argus: regrouping stopped: {error}", file=sys.stderr)
    open_ids = {w.workspace_id for w in workspaces}
    write_labels_guarded(labels_file,
                         {i: label for i, label in set_by_argus.items() if i in open_ids})


def as_workspace(workspace_id: str, label: str, checkout: Checkout | None,
                 cwd: Path | None) -> Workspace:
    cwd_name = cwd.name if cwd else None
    if checkout is None:
        return Workspace(workspace_id, label, None, None, cwd_name)
    return Workspace(workspace_id, label, checkout.root, checkout.source, cwd_name)


def read_labels_guarded(labels_file: Path) -> dict[str, str]:
    try:
        stored: Any = json.loads(labels_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # none yet, or unreadable: argus only forgets what it named
        return {}
    if not isinstance(stored, dict):
        return {}
    return {str(i): label for i, label in stored.items() if isinstance(label, str)}


def write_labels_guarded(labels_file: Path, labels: Mapping[str, str]) -> None:
    try:
        labels_file.parent.mkdir(parents=True, exist_ok=True)
        labels_file.write_text(json.dumps(labels), encoding="utf-8")
    except OSError as error:
        print(f"argus: labels not saved: {error}", file=sys.stderr)


def report_status_guarded(herdr: Herdr, workspace_id: str, checkout: Checkout | None,
                          symbols: Symbols) -> None:
    try:
        tokens = tokens_for(checkout, read_counts(checkout.root) if checkout else None, symbols)
        if tokens is not None:
            herdr.report(workspace_id, tokens)
    except Exception as error:  # in a pool thread anything uncaught would vanish silently
        print(f"argus: status of {workspace_id} not reported: {error!r}", file=sys.stderr)


def ids_present(value: object) -> frozenset[str]:
    return frozenset({value}) if isinstance(value, str) and value else frozenset()
