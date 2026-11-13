"""Run by herdr on startup and on each subscribed event (see herdr-plugin.toml)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from argus.herdr import Herdr, HerdrError
from argus.lock import RefreshLock
from argus.refresh import NO_WORK, Work, refresh, work_for_event
from argus.settings import Symbols, load_symbols


def main() -> int:
    socket_path = os.environ.get("HERDR_SOCKET_PATH")
    if not socket_path:
        print("argus: HERDR_SOCKET_PATH is not set; argus runs as a herdr plugin",
              file=sys.stderr)
        return 0
    work = work_for_event(os.environ.get("HERDR_PLUGIN_EVENT"),
                          json_from_environment("HERDR_PLUGIN_EVENT_JSON"),
                          json_from_environment("HERDR_PLUGIN_CONTEXT_JSON"))
    if work.is_empty():  # most agent status changes; skip the lock and the queue
        return 0
    lock = RefreshLock(state_directory())
    herdr = Herdr(socket_path)
    config_dir = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
    symbols = load_symbols(Path(config_dir) if config_dir else None)
    while True:
        if not lock.try_acquire():
            lock.queue(work)
            # the holder may have taken the queue and released before we wrote to it
            if not lock.try_acquire():
                return 0  # still held: the holder takes the queue before or after its release
            work = lock.take_queued() or NO_WORK
        try:
            next_work: Work | None = work
            while next_work is not None:
                refresh_guarded(herdr, next_work, symbols)
                next_work = lock.take_queued()
        finally:
            lock.release()
        # work queued between the last take and the release would otherwise wait for the next event
        leftover = lock.take_queued()
        if leftover is None:
            return 0
        work = leftover


def refresh_guarded(herdr: Herdr, work: Work, symbols: Symbols) -> None:
    try:
        refresh(herdr, work, symbols)
    except HerdrError as error:  # herdr unreachable or refusing; the next event tries again
        print(f"argus: refresh failed: {error}", file=sys.stderr)


def json_from_environment(name: str) -> Mapping[str, Any]:
    try:
        value: Any = json.loads(os.environ.get(name) or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def state_directory() -> Path:
    configured = os.environ.get("HERDR_PLUGIN_STATE_DIR")
    return Path(configured) if configured else Path(tempfile.gettempdir()) / "argus"


if __name__ == "__main__":
    sys.exit(main())
