# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --status in_progress  # Claim work
bd close <id>         # Complete work
bd sync               # Sync with git
```

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds


<!-- deadweight:init -->
## Dead Ends Registry (deadweight)

Before attempting any non-trivial coding approach, check for known dead ends:

```bash
curl -s "https://deadweight.dev/query?repo=henstarr/deadweight&approach={keywords}"
```

If results come back, read the `reason` field — skip that approach.

When you abandon an approach after 3+ turns, log the dead end:

```bash
curl -s -X POST https://deadweight.dev/log \
  -H "Content-Type: application/json" \
  -d '{"repo":"henstarr/deadweight","approach":"{what you tried}","reason":"{why it failed}","turns_wasted":{N}}'
```

Fields: `repo` (required), `approach` (required), `path`, `reason`, `turns_wasted`, `agent`, `version`, `task_id`.
