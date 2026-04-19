# deadweight — Agent Integration

> Query before you try. Log when you fail. Save the next agent from your mistakes.

deadweight is a repo-local registry of **dead ends** — specific coding approaches that AI agents tried and abandoned. It lives in `.deadweight/` inside the repo. The `deadends.jsonl` file is committed to git; every clone inherits the history.

## Step 0: Detect whether this repo has deadweight configured

Check for either signal:

- A `.deadweight/` directory at the repo root.
- A `<!-- deadweight:init -->` marker inside `CLAUDE.md` or `AGENTS.md`.

If either is present, skip to the query/log workflow below.

## If not configured: initialize it

```bash
uv tool install deadweight && dw init
```

`dw init` creates `.deadweight/` (with `deadends.jsonl` and a SQLite index), appends a Dead Ends Registry section to `AGENTS.md` and `CLAUDE.md`, and installs Claude Code `SessionStart` / `Stop` hooks in `.claude/settings.json`. It auto-detects the repo name from the git remote. Run once, commit the result.

If you cannot install packages, you can still operate by appending to `.deadweight/deadends.jsonl` manually. One dead end per line:

```json
{"repo":"owner/repo","approach":"monkeypatching Query._execute","reason":"breaks transaction isolation","turns_wasted":14,"agent":"claude-code"}
```

## When to query (BEFORE attempting an approach)

Before you try any non-trivial approach — especially one involving framework internals, monkey-patching, or undocumented APIs — check for known dead ends:

```bash
dw query --approach "keywords describing what you're about to try"
```

Example:

```bash
dw query --approach "monkeypatch Query._execute"
```

**If results come back**: read the `reason` field on each result. If the reason applies to your situation, skip that approach entirely. You just saved 5–30 LLM turns.

**If no results come back**: proceed normally. You're in uncharted territory.

Useful filters: `--path <dir>`, `--agent claude-code`, `--limit N`, `--json`.

## When to log (AFTER abandoning an approach)

When you abandon an approach after **3 or more turns**, log it so the next agent doesn't repeat the mistake:

```bash
dw log \
  --approach "what you tried — be specific" \
  --reason "why it failed — one sentence" \
  --turns-wasted N \
  --path path/to/file-or-dir
```

Optional: `--agent claude-code`, `--version <sha>`, `--task-id <id>`.

### What makes a good dead end log?

- **Be specific**: "monkeypatching Query._execute" not "tried changing the query"
- **Name the function/file/API**: future agents search by these keywords
- **State the reason clearly**: "breaks transaction isolation" not "didn't work"
- **Include turns wasted**: this quantifies the economic cost

## Schema

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

`id` and `created_at` are assigned when the entry is written.
