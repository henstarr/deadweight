<p align="center">
  <img width="1774" height="887" alt="deadweight" src="https://github.com/user-attachments/assets/173807dc-515b-466d-88e1-0f93812f19af" />
</p>

**The map of where not to go.** 

It's a repo-local registry of dead ends — approaches that didn't work — committed to git alongside your code. Every clone inherits the map. Every agent (Claude Code, Cursor, Copilot, aider, whatever) that can shell out benefits from it.

No server. No network. No auth. Just a `.jsonl` file and a CLI.

## Install

```bash
uv tool install git+https://github.com/henstarr/deadweight
```

Installs `dw` on your PATH. Always pulls the latest from `main`.

## Quick start

```bash
cd your-repo
dw init
```

That's it. `dw init` does everything:

1. Creates `.deadweight/` with an empty registry
2. Appends a Dead Ends section to `AGENTS.md` and `CLAUDE.md` (creates them if missing)
3. Installs Claude Code `SessionStart` + `Stop` hooks in `.claude/settings.json`

Then commit the result so every clone has the same setup:

```bash
git add .deadweight/ AGENTS.md CLAUDE.md .claude/settings.json
git commit -m "chore: init deadweight"
```

## How hooks work

After `dw init`, Claude Code fires two hooks automatically — no manual steps required.

**On session start** (`SessionStart` hook):

```
[deadweight] 3 dead ends logged in this repo. Query before non-trivial approaches: `dw query --approach ...`. Log abandoned approaches: `dw log --approach ...`.

abc12345  owner/repo  monkeypatching Query._execute
def67890  owner/repo  direct SQLite writes to bypass ORM
...
```

Claude sees the count and relevant dead ends before writing a single line of code. If files are changed in your working tree, the hook surfaces dead ends matching those paths first; otherwise it shows the 5 most recent.

**On session end** (`Stop` hook):

```
[deadweight] 3 dead ends on record. Log any abandoned approaches with `dw log`.
```

A short reminder to log anything that failed before closing out.

Both hooks are non-blocking — they never prevent Claude from responding.

## Core workflow

**Before trying an approach:**

```bash
dw query --approach "monkeypatch Query._execute"
```

If a match comes back, skip it. The reason is in the record. Search covers both the approach description and the failure reason.

**After giving up on an approach (3+ turns wasted):**

```bash
dw log \
  --approach "monkeypatching Query._execute" \
  --reason "breaks transaction isolation in tests" \
  --turns-wasted 14
```

`dw log` writes to disk immediately — the entry is available to every agent in the same clone right away.

**Share with your team:**

```bash
dw sync          # git add + commit the jsonl
git push
```

`dw sync` is only needed when you want to push the knowledge to a shared remote. `dw log` already persists locally — teammates on the same machine or in the same clone see it immediately after `git pull` triggers an automatic index rebuild.

**If an approach is unblocked (library update, code change):**

```bash
dw update <id> --resolved
```

Marks the dead end as resolved. It stops appearing in queries and at session start. The history is preserved in the JSONL for auditing.

## All commands

| Command | What it does |
|---------|-------------|
| `dw init` | Set up `.deadweight/`, inject docs, install hooks |
| `dw log --approach "..." --reason "..." --turns-wasted N` | Record a dead end |
| `dw query --approach "..."` | Search dead ends (FTS with BM25 ranking) |
| `dw update <id> --resolved` | Mark a dead end as resolved |
| `dw list` | Recent unresolved dead ends (default: 20) |
| `dw show <id>` | Full JSON for one entry |
| `dw insights` | Aggregate report: total turns wasted, hot paths, agent breakdown |
| `dw sync` | `git add` + commit the jsonl (for sharing; `dw log` already persists locally) |
| `dw rebuild` | Rebuild SQLite index from jsonl (runs automatically on `git pull`) |
| `dw check` | One-line status used by hooks |

## How it works

```
.deadweight/
  deadends.jsonl   # source of truth — committed to git
  deadends.db      # SQLite index — gitignored, rebuilt automatically
  config.yaml      # repo id, sync branch
```

Writes append to the jsonl. Reads hit the SQLite FTS5 index, which rebuilds itself whenever the jsonl is newer (e.g. after `git pull`). Search uses BM25 ranking over both the approach and reason fields — a query for "module import failure" will match entries that describe it differently.

Committing the jsonl is the whole point — dead-end knowledge travels with the code.

## Cross-agent sharing

The `agent` field tracks which tool logged a dead end. An approach abandoned by Cursor gets seen by Claude Code in the same repo. A dead end logged by one developer's aider session shows up at the next developer's session start. The JSONL is the shared memory layer.

```bash
dw log --approach "..." --agent cursor
```

`dw query` and `dw list` show all entries regardless of which agent logged them. You can filter with `--agent` if needed.

## Schema

| Field | Required | Notes |
|-------|----------|-------|
| `repo` | yes | Auto-detected from git remote |
| `approach` | yes | What was tried — the primary search field |
| `reason` | no | Why it failed (also searched by `dw query`) |
| `turns_wasted` | no | LLM turns spent before abandoning |
| `path` | no | File or directory the approach touched (enables path-relevant hook output) |
| `agent` | no | `claude-code`, `cursor`, `copilot`, `aider`, `windsurf`, `other` |
| `version` | no | Commit SHA or release tag |
| `task_id` | no | External task id (SWE-bench, issue #) |

## Other agents

Any agent that can shell out works the same way. The `AGENTS.md` and `CLAUDE.md` sections injected by `dw init` tell your agent to run `dw query` before trying and `dw log` after giving up. For non-Claude agents, the hooks won't auto-fire, but the instructions in those files serve the same purpose.

Pass `--no-hooks` to skip hook installation if you're using a different agent or setting up hooks manually:

```bash
dw init --no-hooks
```

## Philosophy

Every AI agent starts from zero — rediscovering every landmine in the repo. deadweight is the infrastructure for the negative space. See [PHILOSOPHY.md](PHILOSOPHY.md).

## Contributing

```bash
uv sync --extra dev
uv run pytest
```

## License

MIT
