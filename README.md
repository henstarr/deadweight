<p align="center">
  <img width="1774" height="887" alt="deadweight" src="https://github.com/user-attachments/assets/173807dc-515b-466d-88e1-0f93812f19af" />
</p>

The biggest gains in agent performance come from eliminating the exploratory phase — the part where an agent discovers what doesn't work before finding what does. Prior research shows agents solve SWE-bench tasks significantly faster when they can query prior solutions. But that only captures the positive signal: what worked. The exploratory phase itself — the dead ends, the wrong files, the APIs that look right but break under load — is thrown away at the end of every session. deadweight captures that negative signal and makes it queryable. It tells your agent what to skip.

deadweight lives inside your repo. No server, no network, no auth. Dead ends are committed to git alongside your code, so every clone of the repo ships with the map of its own landmines.

## Quick start

```bash
pip install deadweight
```

```bash
cd your-repo
dw init
```

`dw init` creates a `.deadweight/` directory, adds a Dead Ends Registry section to `AGENTS.md` and `CLAUDE.md`, and installs Claude Code `SessionStart` / `Stop` hooks.

Check before you try:

```bash
dw query --approach "monkeypatch Query._execute"
```

Log when you give up:

```bash
dw log \
  --approach "monkeypatching Query._execute to inject custom SQL" \
  --reason "breaks transaction isolation in nested atomic blocks" \
  --turns-wasted 14 \
  --path django/db/models/sql/compiler.py
```

See where your agents waste time:

```bash
dw insights
```

Commit the jsonl so every teammate and every future agent sees it:

```bash
dw sync
```

## How it works

`dw init` creates a single directory:

```
.deadweight/
  deadends.jsonl   # source of truth — committed to git
  deadends.db      # SQLite index — gitignored, rebuilt from jsonl
  config.yaml      # repo identifier and defaults
```

Every `dw log` appends a line to `deadends.jsonl` and updates the SQLite index. Every `dw query` reads the index — and rebuilds it automatically if the jsonl is newer.

Committing the jsonl is the whole point. When a teammate clones the repo, their agents inherit every dead end ever recorded. No account, no sync service, no central registry — the knowledge travels with the code.

`dw sync` is a convenience: `git add .deadweight/deadends.jsonl && git commit`. It does not push.

## The schema

| Field | Required | Description |
|-------|----------|-------------|
| `repo` | yes | Repository identifier (auto-detected from git remote) |
| `approach` | yes | What was tried — the primary search field |
| `path` | no | File or directory path prefix |
| `reason` | no | Why it failed (one sentence) |
| `turns_wasted` | no | LLM turns spent before abandoning |
| `agent` | no | `claude-code`, `openclaw`, `cursor`, `copilot`, `aider`, `windsurf`, `other` |
| `version` | no | Commit SHA or release version |
| `task_id` | no | External task ID (SWE-bench ID, issue number) |

`id` and `created_at` are assigned on log.

## Agent integration

`dw init` writes a "Dead Ends Registry" section into `AGENTS.md` and `CLAUDE.md` at the repo root. That section tells any agent entering the repo to run `dw query` before attempting a non-trivial approach and `dw log` after abandoning one. For Claude Code, `dw init` also installs `SessionStart` and `Stop` hooks in `.claude/settings.json` that call `dw check` as a non-blocking reminder.

Any agent that can shell out works identically — Claude Code, OpenClaw, Cursor, Copilot, Aider, Windsurf. The CLI is the only integration surface.

## Philosophy

Every AI agent starts from zero. The exploratory phase — the dead ends, the wrong files, the APIs that look right but break under load — is the most expensive part of every agentic coding session, and it's thrown away at the end of every one. deadweight is the infrastructure for the negative space. The map of where not to go.

See [PHILOSOPHY.md](PHILOSOPHY.md).

## Contributing

```bash
git clone https://github.com/henstarr/deadweight
cd deadweight
pip install -e ".[dev]"
pytest
```

## License

MIT
