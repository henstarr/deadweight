# Project Instructions

<!-- deadweight:init -->
## Dead Ends Registry (deadweight)

This project uses [deadweight](https://deadweight.dev) to track approaches that failed.

**Before trying a non-trivial approach**, query for known dead ends:

```bash
curl -s "https://deadweight.dev/query?repo=henstarr/deadweight&approach={keywords}"
```

If the `reason` field matches your situation, skip that approach entirely.

**When you abandon an approach after 3+ turns**, log it so the next agent doesn't repeat it:

```bash
curl -s -X POST https://deadweight.dev/log \
  -H "Content-Type: application/json" \
  -d '{"repo":"henstarr/deadweight","approach":"{what you tried}","reason":"{why it failed}","turns_wasted":{N}}'
```
