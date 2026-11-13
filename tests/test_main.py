"""The entry point herdr runs: reads its environment and refreshes, or queues when busy."""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from argus.__main__ import main
from argus.lock import RefreshLock
from argus.refresh import Work


class EntryPoint(unittest.TestCase):
    def test_outside_herdr_it_explains_and_does_nothing(self) -> None:
        errors = io.StringIO()
        with mock.patch.dict("os.environ", {}, clear=True), redirect_stderr(errors):
            self.assertEqual(main(), 0)
        self.assertIn("HERDR_SOCKET_PATH", errors.getvalue())

    def test_a_busy_refresh_gets_the_work_queued(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            holder = RefreshLock(Path(state))
            self.assertTrue(holder.try_acquire())
            self.addCleanup(holder.release)
            environment = {"HERDR_SOCKET_PATH": "/unused", "HERDR_PLUGIN_STATE_DIR": state,
                           "HERDR_PLUGIN_EVENT": "workspace.focused",
                           "HERDR_PLUGIN_CONTEXT_JSON": '{"workspace_id": "w7"}'}
            with mock.patch.dict("os.environ", environment, clear=True), \
                    mock.patch("argus.__main__.refresh") as refresh:
                self.assertEqual(main(), 0)
            refresh.assert_not_called()
            self.assertEqual(holder.take_queued(), Work(True, False, frozenset({"w7"})))

    def test_an_event_needing_no_work_touches_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            environment = {"HERDR_SOCKET_PATH": "/unused", "HERDR_PLUGIN_STATE_DIR": state,
                           "HERDR_PLUGIN_EVENT": "pane.agent_status_changed",
                           "HERDR_PLUGIN_EVENT_JSON": '{"data": {"agent_status": "working"}}'}
            with mock.patch.dict("os.environ", environment, clear=True):
                self.assertEqual(main(), 0)
            self.assertEqual(list(Path(state).iterdir()), [])

    def test_an_unreachable_herdr_is_reported_without_a_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            environment = {"HERDR_SOCKET_PATH": "/nonexistent/herdr.sock",
                           "HERDR_PLUGIN_STATE_DIR": state}
            errors = io.StringIO()
            with mock.patch.dict("os.environ", environment, clear=True), redirect_stderr(errors):
                self.assertEqual(main(), 0)
            self.assertIn("argus: refresh failed", errors.getvalue())

    def test_work_queued_as_the_holder_releases_is_still_done(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            holder = RefreshLock(Path(state))
            self.assertTrue(holder.try_acquire())
            first_try = RefreshLock.try_acquire

            def holder_releases_after_first_try(lock: RefreshLock) -> bool:
                acquired = first_try(lock)
                holder.release()  # the holder finishes in between: it never sees the queue
                return acquired

            environment = {"HERDR_SOCKET_PATH": "/unused", "HERDR_PLUGIN_STATE_DIR": state,
                           "HERDR_PLUGIN_EVENT": "workspace.focused",
                           "HERDR_PLUGIN_CONTEXT_JSON": '{"workspace_id": "w7"}'}
            with mock.patch.dict("os.environ", environment, clear=True), \
                    mock.patch("argus.__main__.refresh") as refresh, \
                    mock.patch.object(RefreshLock, "try_acquire", autospec=True,
                                      side_effect=holder_releases_after_first_try):
                self.assertEqual(main(), 0)
            self.assertEqual([c.args[1] for c in refresh.call_args_list],
                             [Work(True, False, frozenset({"w7"}))])

    def test_queued_work_runs_before_the_lock_is_released(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            RefreshLock(Path(state)).queue(Work(True, False, frozenset()))
            environment = {"HERDR_SOCKET_PATH": "/unused", "HERDR_PLUGIN_STATE_DIR": state,
                           "HERDR_PLUGIN_EVENT": "workspace.focused",
                           "HERDR_PLUGIN_CONTEXT_JSON": '{"workspace_id": "w7"}'}
            with mock.patch.dict("os.environ", environment, clear=True), \
                    mock.patch("argus.__main__.refresh") as refresh:
                self.assertEqual(main(), 0)
            self.assertEqual([c.args[1] for c in refresh.call_args_list],
                             [Work(True, False, frozenset({"w7"})),
                              Work(True, False, frozenset())])
            after = RefreshLock(Path(state))
            self.assertTrue(after.try_acquire())
            after.release()


if __name__ == "__main__":
    unittest.main()
