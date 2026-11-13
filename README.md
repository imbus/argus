# argus

In Greek myth, Argus Panoptes was a herdsman with a hundred eyes, set to guard Hera's cow Io,
until Hermes (the Romans' Mercury, and himself the god of herdsmen) lulled every eye to sleep and
slew him. Mercury's chemical symbol, Hg, is Mercurial's command name. argus keeps an eye on every
share of your Mercurial herd, and unlike the original, stays awake.

argus is a [herdr](https://herdr.dev) plugin. For every workspace in an hg checkout it reports
whether there's uncommitted work and whether there are commits that aren't pushed yet, and it
keeps workspaces opened in `hg share`s directly below the workspace of the repository they share:

```
● myrepo          *2
● ├ myrepo-feature *12 ?1
● ├ myrepo-fix     ↑2
● └ myrepo-spike   *1 ↑3
● notes  main ✓
```

- `*N`: N tracked files changed, added, removed or missing (`hg status -mard`).
- `?N`: N untracked files (`hg status -u`).
- `↑N`: N commits not pushed yet, i.e. still in the draft phase.
- `├ name` / `└ name`: a share of the repository above it, named after its folder; `└` marks the
  last one, so the marks draw a tree when each workspace takes one row.

### How it differs from [herdr-hg](https://github.com/mpzarde/herdr-hg)

herdr-hg is a full hg worktree workflow: it creates, opens, removes and prunes shares with their
bookmarks, checks for incoming changesets and shows interrupted rebases and merges. argus only
watches the checkouts you already have:

- **Nothing else to set up.** argus needs `hg` and Python and nothing more; you only add its
  tokens to your sidebar rows. herdr-hg also needs `jq`, `nc` and `perl` on macOS and Linux, and
  its setup step adds hooks to `~/.hgrc` and key bindings and sidebar rows to herdr's
  `config.toml`.
- **A tree of shares.** Both keep a share's workspace below its repository's. herdr-hg labels each
  share `↳ bookmark`; argus names it after its folder and draws an actual tree, with `└` on the
  last share.
- **Untracked files in the sidebar.** argus shows `?N` as a token of its own; herdr-hg lists
  untracked files only in its details popup.

## Install

```
herdr plugin install imbus/argus
```

It needs `hg` and Python 3.12 or later on `PATH` (`python3`; on Windows the `py` launcher).

Then show its values in the sidebar, for example as one row in your herdr `config.toml`:

```toml
[ui.sidebar.spaces]
rows = [[
  "state_icon", { token = "workspace", bold = true },
  { token = "branch", fg = "#89b4fa" }, { token = "git_status" },
  { token = "$hg_dirty", fg = "#f9e2af" }, { token = "$hg_untracked", dim = true },
  { token = "$hg_unpushed", fg = "#fab387" },
]]
```

`branch` and `git_status` are herdr's own and only filled in git repositories; argus's values are
only filled in hg ones, so the same row works for both. The tree marks are part of the workspace
names, so they show wherever herdr shows those; keep the agents panel to one row per agent too
(`[ui.sidebar.agents] rows = [["state_icon", "workspace", "tab", "agent"]]`) and the tree stays
unbroken there as well.

## Values

| Token | Value |
|---|---|
| `$hg_dirty` | `*N` tracked files with uncommitted changes, empty when there are none |
| `$hg_untracked` | `?N` untracked files, empty when there are none |
| `$hg_unpushed` | `↑N` draft commits in the working copy's ancestry, empty when there are none |
| `$hg_branch` | the working copy's branch |
| `$hg_bookmark` | the active bookmark, empty if none |
| `$hg_source` | the folder name of the repository this is a share of, empty if it isn't one |

## Symbols

The symbols are configurable in `config.toml` in the plugin's config folder
(`herdr plugin config-dir imbus.argus`); anything left out keeps its default:

```toml
[symbols]
dirty = "*"
untracked = "?"
unpushed = "↑"
tree_middle = "├"
tree_last = "└"
```

Changes apply from the next refresh; names with the default marks are still recognised as
argus's after you change them. Problems with the file show up in `herdr plugin log list`.

## When it updates

When herdr starts, when a workspace opens, closes or gets focus, and when an agent in a workspace
finishes or waits for input. A commit you make by hand shows up the next time you switch to the
workspace.

## Grouping

A workspace belongs to an hg share when the pane of its active tab is inside one
(`.hg/sharedpath`). While the shared repository has a workspace of its own, argus moves the share's
workspace directly below it (shares sorted by folder name) and names it `├ <folder>`, or
`└ <folder>` for the last one; otherwise the share keeps its place and its plain folder name.
Workspaces that aren't shares never move, and a share you renamed yourself keeps your name.

## What it doesn't do

- No network access: "pushed" means the commit is public, hg's record of what was pushed.
- No hooks in `~/.hgrc`, no changes to herdr's `config.toml`, no key bindings.
- No creating or removing shares.

Windows support is untested so far.

## Development

```
mise run test   # unit tests, and integration tests against real hg repositories
mise run lint   # ruff and strict pyrefly
```

To try a local checkout: `herdr plugin link <path>`.
