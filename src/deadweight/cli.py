"""deadweight — repo-local dead ends registry. CLI-first, git-native.

Usage:
    dw init                    Create .deadweight/ in current repo
    dw log --approach "..."    Log an abandoned approach
    dw query --approach "..."  Search known dead ends
    dw list                    Recent dead ends
    dw show <id>               Full entry
    dw insights [--repo ...]   Aggregate report
    dw rebuild                 Rebuild SQLite index from jsonl
    dw sync                    Commit .deadweight/deadends.jsonl
    dw check                   Summary line (used by Claude Code Stop hook)
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from pathlib import Path

from . import __version__
from .db import (
    JSONL_FILE,
    append_dead_end,
    find_store,
    get_dead_end,
    get_repo_insights,
    init_store,
    query_dead_ends,
    read_config,
    rebuild_index,
    recent_dead_ends,
    require_store,
)
from .models import DeadEndCreate

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("deadweight")


# ---------------------------------------------------------------------------
# Repo detection + markdown injection
# ---------------------------------------------------------------------------


def _detect_repo(root: Path) -> str:
    """Infer `owner/repo` from git remote origin, fall back to directory name."""
    try:
        url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        m = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
        if m:
            return m.group(1)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return root.name


def _find_repo_root(start: Path) -> Path:
    """Return the git repo root, or `start` if not inside a repo."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            return Path(out)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return start


_MARKER = "<!-- deadweight:init -->"

_AGENTS_SECTION = """{marker}
## Dead Ends Registry (deadweight)

This repo tracks abandoned approaches in `.deadweight/deadends.jsonl` (committed).

**Before** attempting any non-trivial coding approach, check for known dead ends:

```bash
dw query --approach "{{keywords}}"
```

If a result matches your situation, skip that approach.

**When** you abandon an approach after 3+ turns, log it:

```bash
dw log --approach "{{what you tried}}" --reason "{{why it failed}}" --turns-wasted {{N}}
```

Optional flags: `--path`, `--task-id`, `--agent`, `--version`.
"""

_CLAUDE_SECTION = _AGENTS_SECTION  # identical content for both files


def _inject_section(path: Path, section: str, default_heading: str) -> bool:
    if path.exists():
        content = path.read_text()
        if _MARKER in content:
            return False
        if content and not content.endswith("\n"):
            content += "\n"
        content += "\n" + section
    else:
        content = f"# {default_heading}\n\n" + section
    path.write_text(content)
    return True


# ---------------------------------------------------------------------------
# Claude Code hook installation
# ---------------------------------------------------------------------------


def _install_claude_hooks(root: Path) -> bool:
    """Install SessionStart + Stop hooks into .claude/settings.json.

    The Stop hook runs `dw check` which prints a short reminder/summary line.
    It is non-blocking by design: Claude Code can't tell whether an approach was
    abandoned without being logged, so this is a prompt, not a gate.
    """
    claude_dir = root / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings = claude_dir / "settings.json"

    data: dict = {}
    if settings.exists():
        try:
            data = json.loads(settings.read_text())
        except json.JSONDecodeError:
            logger.warning("Could not parse %s, leaving untouched", settings)
            return False

    hooks = data.setdefault("hooks", {})

    def _already_present(entries: list, needle: str) -> bool:
        for entry in entries or []:
            for h in entry.get("hooks", []):
                if needle in h.get("command", ""):
                    return True
        return False

    changed = False

    session_start = hooks.setdefault("SessionStart", [])
    if not _already_present(session_start, "dw check"):
        session_start.append({
            "matcher": "",
            "hooks": [{"type": "command", "command": "dw check --session-start"}],
        })
        changed = True

    stop_hooks = hooks.setdefault("Stop", [])
    if not _already_present(stop_hooks, "dw check"):
        stop_hooks.append({
            "matcher": "",
            "hooks": [{"type": "command", "command": "dw check"}],
        })
        changed = True

    if changed:
        settings.write_text(json.dumps(data, indent=2) + "\n")
    return changed


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    root = _find_repo_root(Path.cwd())
    repo = args.repo or _detect_repo(root)

    store = init_store(root, repo)
    print(f"deadweight: initialized {store.relative_to(root)} for repo '{repo}'")

    agents_text = _AGENTS_SECTION.format(marker=_MARKER)
    claude_text = _CLAUDE_SECTION.format(marker=_MARKER)

    if _inject_section(root / "AGENTS.md", agents_text, "Agent Instructions"):
        print("  AGENTS.md: added deadweight section")
    else:
        print("  AGENTS.md: already configured, skipped")

    if _inject_section(root / "CLAUDE.md", claude_text, "Project Instructions"):
        print("  CLAUDE.md: added deadweight section")
    else:
        print("  CLAUDE.md: already configured, skipped")

    if args.no_hooks:
        print("  .claude/settings.json: skipped (--no-hooks)")
    else:
        if _install_claude_hooks(root):
            print("  .claude/settings.json: installed SessionStart + Stop hooks")
        else:
            print("  .claude/settings.json: hooks already present")

    print(
        "\nNext: commit .deadweight/ to git so agents in every clone see the same dead ends."
    )
    return 0


def _resolve_repo(store: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    cfg = read_config(store)
    if "repo" in cfg:
        return cfg["repo"]
    return _detect_repo(_find_repo_root(Path.cwd()))


def cmd_log(args: argparse.Namespace) -> int:
    store = require_store()
    repo = _resolve_repo(store, args.repo)

    entry = DeadEndCreate(
        repo=repo,
        path=args.path,
        approach=args.approach,
        reason=args.reason,
        turns_wasted=args.turns_wasted,
        agent=args.agent,
        version=args.version,
        task_id=args.task_id,
    )
    dead_end = append_dead_end(store, entry)

    if args.json:
        print(json.dumps({"id": dead_end.id, "status": "logged"}))
    else:
        print(f"logged {dead_end.id}  {entry.approach[:80]}")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    store = require_store()
    repo = args.repo or (read_config(store).get("repo") if not args.all_repos else None)

    results = query_dead_ends(
        store,
        repo=repo,
        path=args.path,
        approach=args.approach,
        agent=args.agent,
        limit=args.limit,
    )

    if args.json:
        payload = {
            "count": len(results),
            "dead_ends": [r.model_dump(exclude_none=True, mode="json") for r in results],
        }
        print(json.dumps(payload, indent=2, default=str))
        return 0

    if not results:
        print("no matches")
        return 0

    for de in results:
        score = f"  (score {de.relevance_score:.2f})" if de.relevance_score is not None else ""
        print(f"{de.id}  {de.repo}{score}")
        print(f"  approach: {de.approach}")
        if de.reason:
            print(f"  reason:   {de.reason}")
        if de.path:
            print(f"  path:     {de.path}")
        if de.turns_wasted:
            print(f"  turns:    {de.turns_wasted}")
        print()
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    store = require_store()
    results = recent_dead_ends(store, limit=args.limit)

    if args.json:
        print(json.dumps(
            [r.model_dump(exclude_none=True, mode="json") for r in results],
            indent=2,
            default=str,
        ))
        return 0

    if not results:
        print("no dead ends logged yet")
        return 0

    for de in results:
        print(f"{de.id}  {de.repo}  {de.approach[:80]}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    store = require_store()
    de = get_dead_end(store, args.id)
    if de is None:
        print(f"no dead end with id '{args.id}'", file=sys.stderr)
        return 1
    print(json.dumps(de.model_dump(exclude_none=True, mode="json"), indent=2, default=str))
    return 0


def cmd_insights(args: argparse.Namespace) -> int:
    store = require_store()
    repo = _resolve_repo(store, args.repo)
    insight = get_repo_insights(store, repo)
    if insight is None:
        print(f"no dead ends for {repo}")
        return 0

    if args.json:
        print(json.dumps(insight.model_dump(), indent=2, default=str))
        return 0

    print(f"repo: {insight.repo}")
    print(f"total dead ends:      {insight.total_dead_ends}")
    print(f"total turns wasted:   {insight.total_turns_wasted}")
    print(f"avg turns per:        {insight.avg_turns_per_dead_end}")
    if insight.top_dead_ends:
        print("\ntop approaches:")
        for d in insight.top_dead_ends:
            print(f"  [{d.occurrences}x, {d.total_turns_wasted} turns] {d.approach[:80]}")
    if insight.most_common_paths:
        print("\nhottest paths:")
        for p in insight.most_common_paths:
            print(f"  [{p.dead_end_count}x] {p.path}")
    if insight.agent_breakdown:
        print("\nby agent:")
        for a, c in insight.agent_breakdown.items():
            print(f"  {a}: {c}")
    return 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    store = require_store()
    n = rebuild_index(store)
    print(f"rebuilt index from {JSONL_FILE}: {n} entries")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    """Commit the jsonl. No push — user controls when to push."""
    store = require_store()
    jsonl = store / JSONL_FILE
    root = _find_repo_root(store.parent)

    try:
        subprocess.run(
            ["git", "-C", str(root), "add", str(jsonl.relative_to(root))],
            check=True,
        )
        # Only commit if there's something to commit
        diff = subprocess.run(
            ["git", "-C", str(root), "diff", "--cached", "--quiet"],
        )
        if diff.returncode == 0:
            print("nothing to sync — jsonl already up to date")
            return 0
        message = args.message or "dw: sync dead ends"
        subprocess.run(
            ["git", "-C", str(root), "commit", "-m", message],
            check=True,
        )
        print("synced .deadweight/deadends.jsonl")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"git sync failed: {e}", file=sys.stderr)
        return 1


def cmd_check(args: argparse.Namespace) -> int:
    """Print a one-line reminder/summary. Used by Claude Code hooks."""
    store = find_store()
    if store is None:
        # Not initialized — stay silent so we don't nag unrelated repos
        return 0

    jsonl = store / JSONL_FILE
    n = 0
    if jsonl.exists():
        n = sum(1 for line in jsonl.read_text().splitlines() if line.strip())

    if args.session_start:
        print(
            f"[deadweight] {n} dead ends logged in this repo. "
            "Query before non-trivial approaches: `dw query --approach ...`. "
            "Log abandoned approaches: `dw log --approach ...`."
        )
    else:
        print(
            f"[deadweight] {n} dead ends on record. "
            "If you abandoned an approach this session, log it with `dw log`."
        )
    return 0


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dw",
        description="deadweight — repo-local dead ends registry for AI coding agents",
    )
    p.add_argument("--version", action="version", version=f"deadweight {__version__}")
    sub = p.add_subparsers(dest="command")

    init_p = sub.add_parser("init", help="Create .deadweight/ in this repo")
    init_p.add_argument("--repo", help="Repository id (default: auto-detect from git remote)")
    init_p.add_argument(
        "--no-hooks",
        action="store_true",
        help="Skip .claude/settings.json hook install",
    )
    init_p.set_defaults(func=cmd_init)

    log_p = sub.add_parser("log", help="Log an abandoned approach")
    log_p.add_argument("--approach", required=True)
    log_p.add_argument("--reason", default=None)
    log_p.add_argument("--turns-wasted", type=int, default=None, dest="turns_wasted")
    log_p.add_argument("--path", default=None)
    log_p.add_argument("--agent", default=None)
    log_p.add_argument("--version", default=None)
    log_p.add_argument("--task-id", default=None, dest="task_id")
    log_p.add_argument("--repo", default=None, help="Override the repo for this entry")
    log_p.add_argument("--json", action="store_true")
    log_p.set_defaults(func=cmd_log)

    q_p = sub.add_parser("query", help="Search known dead ends")
    q_p.add_argument("--approach", default=None)
    q_p.add_argument("--path", default=None)
    q_p.add_argument("--agent", default=None)
    q_p.add_argument("--repo", default=None)
    q_p.add_argument("--all-repos", action="store_true", dest="all_repos")
    q_p.add_argument("--limit", type=int, default=10)
    q_p.add_argument("--json", action="store_true")
    q_p.set_defaults(func=cmd_query)

    l_p = sub.add_parser("list", help="Recent dead ends across the store")
    l_p.add_argument("--limit", type=int, default=20)
    l_p.add_argument("--json", action="store_true")
    l_p.set_defaults(func=cmd_list)

    s_p = sub.add_parser("show", help="Full entry for a dead end id")
    s_p.add_argument("id")
    s_p.set_defaults(func=cmd_show)

    i_p = sub.add_parser("insights", help="Aggregate report for a repo")
    i_p.add_argument("--repo", default=None)
    i_p.add_argument("--json", action="store_true")
    i_p.set_defaults(func=cmd_insights)

    r_p = sub.add_parser("rebuild", help="Rebuild SQLite index from jsonl")
    r_p.set_defaults(func=cmd_rebuild)

    sync_p = sub.add_parser("sync", help="git-add + commit the jsonl")
    sync_p.add_argument("-m", "--message", default=None)
    sync_p.set_defaults(func=cmd_sync)

    c_p = sub.add_parser("check", help="One-line status (used by Claude Code hooks)")
    c_p.add_argument("--session-start", action="store_true", dest="session_start")
    c_p.set_defaults(func=cmd_check)

    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(0)
    try:
        rc = args.func(args)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
