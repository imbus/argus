"""Where each workspace belongs in the sidebar and what it's called: pure, no herdr calls."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from argus.settings import Symbols


@dataclass(frozen=True)
class Workspace:
    workspace_id: str
    label: str
    folder: Path | None  # the hg checkout's root
    source: Path | None
    cwd_name: str | None = None  # the pane's folder, which herdr names workspaces after


@dataclass(frozen=True)
class Rename:
    workspace_id: str
    label: str


@dataclass(frozen=True)
class Move:
    workspace_id: str
    insert_index: int


def desired_order(workspaces: Sequence[Workspace]) -> list[str]:
    shares_by_source = shares_with_open_source(workspaces)
    attached = {w.workspace_id for shares in shares_by_source.values() for w in shares}
    order: list[str] = []
    for workspace in workspaces:
        if workspace.workspace_id in attached:
            continue
        order.append(workspace.workspace_id)
        if is_source(workspace) and workspace.folder in shares_by_source:
            order += [w.workspace_id for w in shares_by_source.pop(workspace.folder)]
    return order


def moves_to(current: Sequence[str], desired: Sequence[str]) -> list[Move]:
    # Left to right: whatever belongs at index i is always to its right, so herdr's
    # "insert before the workspace now at index i" means exactly position i.
    simulated = list(current)
    moves: list[Move] = []
    for index, workspace_id in enumerate(desired):
        if simulated[index] != workspace_id:
            simulated.remove(workspace_id)
            simulated.insert(index, workspace_id)
            moves.append(Move(workspace_id, index))
    return moves


def share_marks(workspaces: Sequence[Workspace], middle: str, last: str) -> dict[str, str | None]:
    marks: dict[str, str | None] = dict.fromkeys(w.workspace_id for w in workspaces)
    for shares in shares_with_open_source(workspaces).values():
        for index, share in enumerate(shares):
            marks[share.workspace_id] = last if index == len(shares) - 1 else middle
    return marks


def renames(workspaces: Sequence[Workspace], symbols: Symbols,
            set_by_argus: Mapping[str, str]) -> list[Rename]:
    # Once renamed, herdr no longer names a workspace after its folder, so argus keeps doing
    # that for the workspaces it renamed; set_by_argus is the label it last gave each.
    marks = share_marks(workspaces, symbols.tree_middle, symbols.tree_last)
    # labels with the default marks stay argus's after someone configures other symbols
    known_marks = {symbols.tree_middle, symbols.tree_last, Symbols.tree_middle, Symbols.tree_last}
    result: list[Rename] = []
    for workspace in workspaces:
        name = workspace.folder.name if workspace.folder else workspace.cwd_name
        if name is None:
            continue
        mark = marks[workspace.workspace_id]
        wanted = f"{mark} {name}" if mark else name
        if workspace.label == wanted:
            continue
        first, _, rest = workspace.label.partition(" ")
        if ((first in known_marks and rest) or workspace.label == name
                or workspace.label == set_by_argus.get(workspace.workspace_id)):
            result.append(Rename(workspace.workspace_id, wanted))
        # otherwise a name the user chose
    return result


def shares_with_open_source(workspaces: Sequence[Workspace]) -> dict[Path, list[Workspace]]:
    open_sources = {w.folder for w in workspaces if is_source(w)}
    shares_by_source: dict[Path, list[Workspace]] = {}
    for workspace in workspaces:
        if workspace.source is not None and workspace.source in open_sources:
            shares_by_source.setdefault(workspace.source, []).append(workspace)
    return {source: sorted(shares, key=folder_name_then_id)
            for source, shares in shares_by_source.items()}


def is_source(workspace: Workspace) -> bool:
    return workspace.folder is not None and workspace.source is None


def folder_name_then_id(workspace: Workspace) -> tuple[str, str]:
    return (workspace.folder.name if workspace.folder else "", workspace.workspace_id)
