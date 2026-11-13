"""The symbols argus shows, configurable in config.toml in herdr's config folder for the plugin."""
from __future__ import annotations

import dataclasses
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILE_NAME = "config.toml"


@dataclass(frozen=True)
class Symbols:
    dirty: str = "*"
    untracked: str = "?"
    unpushed: str = "↑"
    tree_middle: str = "├"
    tree_last: str = "└"


def load_symbols(config_dir: Path | None) -> Symbols:
    if config_dir is None:
        return Symbols()
    config = read_config_guarded(config_dir / CONFIG_FILE_NAME)
    configured = config.get("symbols", {})
    if not isinstance(configured, dict):
        note(f"{CONFIG_FILE_NAME}: [symbols] must be a table; using the default symbols")
        return Symbols()
    known = {field.name for field in dataclasses.fields(Symbols)}
    usable = {name: value for name, value in configured.items()
              if name in known and isinstance(value, str)}
    for name in sorted(set(configured) - set(usable)):
        note(f"{CONFIG_FILE_NAME}: ignoring symbols.{name} (known, text-valued: "
             f"{', '.join(sorted(known))})")
    return Symbols(**usable)


def read_config_guarded(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as config:
            return tomllib.load(config)
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as error:
        note(f"{path}: {error}; using the default symbols")
        return {}


def note(message: str) -> None:
    print(f"argus: {message}", file=sys.stderr)
