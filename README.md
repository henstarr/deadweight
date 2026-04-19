<p align="center">
  <img width="1774" height="887" alt="deadweight" src="https://github.com/user-attachments/assets/173807dc-515b-466d-88e1-0f93812f19af" />
</p>

**The map of where not to go.** Your agent just spent 14 turns monkeypatching `Query._execute` before giving up. The next agent will repeat it. deadweight is a repo-local registry of dead ends — approaches that didn't work — committed to git alongside your code. Every clone inherits the landmine map.

No server. No network. No auth. Just a jsonl file and a CLI.

## Install

```bash
uv tool install deadweight
```

Installs `dw` on your PATH.

## Quick start

```bash
cd your-repo
dw init                                   # creates .deadweight/, wires AGENTS.md + CLAUDE.md, installs hooks

dw query --approach "monkeypatch Query._execute"   # before you try

dw log \
  --approach "monkeypatching Query._execute" \
  --reason "breaks transaction isolation" \
  --turns-wasted 14                       # after you give up

dw sync                                   # git add + commit the jsonl
```

Run `dw --help` for the rest (`list`, `show`, `insights`, `rebuild`).

## How it works

```
.deadweight/
  deadends.jsonl   # source of truth — committed to git
  deadends.db      # SQLite index — gitignored, auto-rebuilt
  config.yaml      # repo id, sync branch
```

Writes append to the jsonl. Reads hit the SQLite index, which auto-rebuilds when the jsonl is newer (e.g. after `git pull`). Committing the jsonl is the whole point: dead-end knowledge travels with the code.

## Schema

| Field | Required | Notes |
|-------|----------|-------|
| `repo` | yes | Auto-detected from git remote |
| `approach` | yes | What was tried — the primary search field |
| `path` | no | File or directory prefix |
| `reason` | no | Why it failed (one sentence) |
| `turns_wasted` | no | LLM turns spent before abandoning |
| `agent` | no | `claude-code`, `openclaw`, `cursor`, `copilot`, `aider`, `windsurf`, `other` |
| `version` | no | Commit SHA or release |
| `task_id` | no | External task id (SWE-bench, issue #) |

## Agent integration

`dw init` appends a Dead Ends Registry section to `AGENTS.md` and `CLAUDE.md`, and installs Claude Code `SessionStart` + `Stop` hooks that remind the agent to query before trying and log after giving up. Any agent that can shell out works identically — Claude Code, OpenClaw, Cursor, Copilot, Aider, Windsurf.

## Philosophy

Every AI agent starts from zero — rediscovering every landmine in the repo. deadweight is the infrastructure for the negative space. See [PHILOSOPHY.md](PHILOSOPHY.md).

## Contributing

```bash
uv sync --extra dev
uv run pytest
```

## License

MIT
