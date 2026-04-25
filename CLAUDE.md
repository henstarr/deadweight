# Project Instructions

<!-- deadweight:init -->
## Dead Ends Registry (deadweight)

This repo tracks abandoned approaches in `.deadweight/deadends.jsonl` (committed).

**Before** attempting any non-trivial coding approach, check for known dead ends:

```bash
dw query --approach "{keywords}"
```

If a result matches your situation, skip that approach.

**When** you abandon an approach after 3+ turns, log it:

```bash
dw log --approach "{what you tried}" --reason "{why it failed}" --turns-wasted {N}
```

Optional flags: `--path`, `--task-id`, `--agent`, `--version`.


For development, use UV for all python commands.
