"""Talking to herdr's socket: one JSON line per request, one JSON line back."""
from __future__ import annotations

import json
import socketserver
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any, ClassVar, override
from unittest import mock

from argus.grouping import Move, Rename
from argus.herdr import Herdr, HerdrError, Pane, WorkspaceInfo, is_windows_pipe, reply_to


class FakeHerdr(socketserver.StreamRequestHandler):
    replies: ClassVar[dict[str, Any]] = {}
    requests: ClassVar[list[dict[str, Any]]] = []

    @override
    def handle(self) -> None:
        request: dict[str, Any] = json.loads(self.rfile.readline())
        FakeHerdr.requests.append(request)
        reply = FakeHerdr.replies.get(request["method"], {"result": {"type": "ok"}})
        self.wfile.write((json.dumps({"id": request["id"], **reply}) + "\n").encode())


@unittest.skipIf(sys.platform == "win32", "Unix socket server")
class SocketClient(unittest.TestCase):
    herdr: Herdr

    @override
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = str(Path(directory.name) / "herdr.sock")
        FakeHerdr.replies = {}
        FakeHerdr.requests = []
        server = socketserver.ThreadingUnixStreamServer(path, FakeHerdr)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.herdr = Herdr(path)

    def test_workspaces_come_back_in_sidebar_order(self) -> None:
        FakeHerdr.replies["workspace.list"] = {"result": {"workspaces": [
            {"workspace_id": "w2", "label": "myrepo", "active_tab_id": "w2:t3"},
            {"workspace_id": "w1", "label": "x", "active_tab_id": "w1:t1"}]}}
        self.assertEqual(self.herdr.workspaces(), [WorkspaceInfo("w2", "myrepo", "w2:t3"),
                                                   WorkspaceInfo("w1", "x", "w1:t1")])

    def test_panes_carry_cwd_and_focus(self) -> None:
        FakeHerdr.replies["pane.list"] = {"result": {"panes": [
            {"workspace_id": "w1", "tab_id": "w1:t1", "cwd": "/r/myrepo", "focused": True,
             "pane_id": "w1:p1"}]}}
        self.assertEqual(self.herdr.panes(), [Pane("w1", "w1:t1", Path("/r/myrepo"), True)])

    def test_report_sends_source_and_null_for_cleared_tokens(self) -> None:
        self.herdr.report("w1", {"hg_dirty": "*1", "hg_branch": None})
        self.assertEqual(FakeHerdr.requests[-1]["method"], "workspace.report_metadata")
        self.assertEqual(FakeHerdr.requests[-1]["params"], {
            "workspace_id": "w1", "source": "imbus.argus",
            "tokens": {"hg_dirty": "*1", "hg_branch": None}})

    def test_move_and_rename_send_their_params(self) -> None:
        self.herdr.move(Move("w3", 1))
        self.herdr.rename(Rename("w3", "└ myrepo-a"))
        self.assertEqual([(r["method"], r["params"]) for r in FakeHerdr.requests], [
            ("workspace.move", {"workspace_id": "w3", "insert_index": 1}),
            ("workspace.rename", {"workspace_id": "w3", "label": "└ myrepo-a"})])

    def test_an_error_reply_raises(self) -> None:
        FakeHerdr.replies["workspace.list"] = {"error": {"code": "x", "message": "nope"}}
        with self.assertRaises(HerdrError):
            self.herdr.workspaces()

    def test_lines_before_the_reply_are_skipped(self) -> None:
        lines = [b'{"event": "workspace.focused"}\n', b'{"id": "argus:0", "result": 1}\n',
                 b'not json\n', b'{"id": "argus:7", "result": {"type": "ok"}}\n']
        self.assertEqual(reply_to("argus:7", lines), lines[3])
        self.assertEqual(reply_to("argus:8", lines), b"")

    def test_an_unreachable_socket_raises(self) -> None:
        with self.assertRaises(HerdrError):
            Herdr("/nonexistent/herdr.sock").workspaces()


class OneRequestAtATime(unittest.TestCase):
    def test_requests_from_several_threads_never_overlap(self) -> None:
        # herdr's Windows named pipe takes one client at a time
        active, most = [0], [0]
        guard = threading.Lock()

        def exchange(_request: bytes, _request_id: str) -> bytes:
            with guard:
                active[0] += 1
                most[0] = max(most[0], active[0])
            time.sleep(0.02)
            with guard:
                active[0] -= 1
            return b'{"result": {"type": "ok"}}\n'

        herdr = Herdr("/unused")
        with mock.patch.object(herdr, "exchange_guarded", side_effect=exchange):
            threads = [threading.Thread(target=herdr.report, args=(f"w{i}", {})) for i in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(most[0], 1)


class WindowsPipe(unittest.TestCase):
    def test_windows_pipe_paths_are_recognised(self) -> None:
        self.assertTrue(is_windows_pipe(r"\\.\pipe\herdr"))
        self.assertTrue(is_windows_pipe(r"\\?\pipe\herdr"))
        self.assertFalse(is_windows_pipe("/run/herdr.sock"))


if __name__ == "__main__":
    unittest.main()
