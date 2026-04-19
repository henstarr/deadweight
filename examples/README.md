# Examples

All examples assume you've run `dw init` at the root of a git repo.

## 1. Query before attempting

```bash
dw query --approach "monkeypatch Query._execute"
```

If a result returns, read the `reason` field. Skip that approach.

## 2. Log when you give up

```bash
dw log \
  --approach "monkeypatching Query._execute to inject custom SQL" \
  --reason "breaks transaction isolation in nested atomic blocks" \
  --turns-wasted 14 \
  --path django/db/models/sql/compiler.py \
  --agent claude-code
```

## 3. Aggregate view

```bash
dw insights
```

Top repeated approaches, hottest paths, agent breakdown. Use `--json` for machine output.

## 4. Commit the jsonl

```bash
dw sync
```

`git add .deadweight/deadends.jsonl && git commit -m "dw: sync dead ends"`. Does not push.

## 5. Recover from a corrupted index

```bash
dw rebuild
```

Rebuilds `.deadweight/deadends.db` from `.deadweight/deadends.jsonl`.

## Raw jsonl fallback

If an agent cannot install `deadweight`, it can still append directly to
`.deadweight/deadends.jsonl`. Each line is a JSON object; the index will be
rebuilt on the next `dw` command:

```
{"id":"abc123def456","repo":"owner/repo","approach":"...","reason":"...","turns_wasted":7,"agent":"claude-code","created_at":"2026-04-19T00:00:00+00:00"}
```

`id` must be unique — any short hex string works.
