"""herdr's socket API: a Unix socket on Linux and macOS, a named pipe on Windows."""
from __future__ import annotations

import contextlib
import itertools
import json
import socket
import threading
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from argus.grouping import Move, Rename

PLUGIN_ID = "imbus.argus"
SOCKET_TIMEOUT_SECONDS = 5
WINDOWS_PIPE_PREFIXES = ("\\\\.\\pipe\\", "\\\\?\\pipe\\")


class HerdrError(Exception):
    pass


@dataclass(frozen=True)
class WorkspaceInfo:
    workspace_id: str
    label: str
    active_tab_id: str


@dataclass(frozen=True)
class Pane:
    workspace_id: str
    tab_id: str
    cwd: Path
    focused: bool


class Herdr:
    def __init__(self, socket_path: str, source: str = PLUGIN_ID) -> None:
        self.socket_path = socket_path
        self.source = source
        self.request_ids = itertools.count(1)
        # herdr's Windows named pipe serves one client at a time; serialising is cheap anywhere
        self.one_request_at_a_time = threading.Lock()

    def workspaces(self) -> list[WorkspaceInfo]:
        result = self.request("workspace.list", {})
        return [WorkspaceInfo(w["workspace_id"], w["label"], w.get("active_tab_id") or "")
                for w in result["workspaces"]]

    def panes(self) -> list[Pane]:
        result = self.request("pane.list", {})
        return [Pane(p["workspace_id"], p.get("tab_id") or "", Path(p["cwd"]),
                     bool(p.get("focused")))
                for p in result["panes"] if p.get("cwd")]

    def report(self, workspace_id: str, tokens: Mapping[str, str | None]) -> None:
        self.request("workspace.report_metadata",
                     {"workspace_id": workspace_id, "source": self.source, "tokens": dict(tokens)})

    def rename(self, rename: Rename) -> None:
        self.request("workspace.rename",
                     {"workspace_id": rename.workspace_id, "label": rename.label})

    def move(self, move: Move) -> None:
        self.request("workspace.move",
                     {"workspace_id": move.workspace_id, "insert_index": move.insert_index})

    def request(self, method: str, params: Mapping[str, Any]) -> Any:
        request_id = f"argus:{next(self.request_ids)}"
        line = json.dumps({"id": request_id, "method": method, "params": params}) + "\n"
        with self.one_request_at_a_time:
            reply_line = self.exchange_guarded(line.encode(), request_id)
        try:
            reply: Any = json.loads(reply_line)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise HerdrError(f"{method}: unreadable reply {reply_line[:200]!r}") from error
        if not isinstance(reply, dict) or "error" in reply or "result" not in reply:
            raise HerdrError(f"{method}: {reply!r}"[:500])
        return reply["result"]

    def exchange_guarded(self, request: bytes, request_id: str) -> bytes:
        try:
            if is_windows_pipe(self.socket_path):
                return exchange_over_pipe(self.socket_path, request, request_id)
            return exchange_over_unix_socket(self.socket_path, request, request_id)
        except OSError as error:
            raise HerdrError(f"herdr socket {self.socket_path}: {error}") from error


def is_windows_pipe(socket_path: str) -> bool:
    return socket_path.startswith(WINDOWS_PIPE_PREFIXES)


def reply_to(request_id: str, lines: Iterable[bytes]) -> bytes:
    # skip anything else herdr writes first; a reply carries its request's id
    for line in lines:
        with contextlib.suppress(json.JSONDecodeError, UnicodeDecodeError):
            reply: Any = json.loads(line)
            if isinstance(reply, dict) and reply.get("id") == request_id:
                return line
    return b""  # connection closed without a reply: request() reports it as unreadable


def exchange_over_unix_socket(socket_path: str, request: bytes, request_id: str) -> bytes:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(SOCKET_TIMEOUT_SECONDS)
        connection.connect(socket_path)
        connection.sendall(request)
        with connection.makefile("rb") as replies:
            return reply_to(request_id, replies)


def exchange_over_pipe(pipe_path: str, request: bytes, request_id: str) -> bytes:
    # shortcut: no timeout on Windows pipe reads (stdlib has none); herdr answers promptly
    with open(pipe_path, "r+b", buffering=0) as pipe:  # noqa: PTH123 (a pipe, not a file path)
        pipe.write(request)
        return reply_to(request_id, pipe)
