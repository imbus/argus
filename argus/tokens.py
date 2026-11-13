"""The values argus reports to herdr's sidebar for one workspace; None clears a token."""
from __future__ import annotations

from argus.hg import Checkout, Counts
from argus.settings import Symbols

TOKEN_NAMES = ("hg_dirty", "hg_untracked", "hg_unpushed", "hg_branch", "hg_bookmark", "hg_source")


def tokens_for(checkout: Checkout | None, counts: Counts | None,
               symbols: Symbols) -> dict[str, str | None] | None:
    if checkout is None:
        return dict.fromkeys(TOKEN_NAMES)
    if counts is None:  # hg failed: keep what the sidebar shows rather than blanking it
        return None
    return {
        "hg_dirty": count_or_none(symbols.dirty, counts.uncommitted),
        "hg_untracked": count_or_none(symbols.untracked, counts.untracked),
        "hg_unpushed": count_or_none(symbols.unpushed, counts.unpushed),
        "hg_branch": checkout.branch,
        "hg_bookmark": checkout.bookmark,
        "hg_source": checkout.source.name if checkout.source else None,
    }


def count_or_none(symbol: str, count: int) -> str | None:
    return f"{symbol}{count}" if count else None
