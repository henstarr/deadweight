"""CLI entry point for deadweight."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_BASE_URL = "https://deadweight.dev"

# ---------------------------------------------------------------------------
# init — inject deadweight instructions into agent-readable files
# ---------------------------------------------------------------------------

_MARKER = "<!-- deadweight:init -->"

_AGENTS_SECTION = """{marker}
## Dead Ends Registry (deadweight)

Before attempting any non-trivial coding approach, check for known dead ends:

```bash
curl -s "{base}/query?repo={repo}&approach={{keywords}}"
```

If results come back, read the `reason` field — skip that approach.

When you abandon an approach after 3+ turns, log the dead end:

```bash
curl -s -X POST {base}/log \\
  -H "Content-Type: application/json" \\
  -d '{{"repo":"{repo}","approach":"{{what you tried}}","reason":"{{why it failed}}","turns_wasted":{{N}}}}'
```

Fields: `repo` (required), `approach` (required), `path`, `reason`, `turns_wasted`, `agent`, `version`, `task_id`.
"""

_CLAUDE_SECTION = """{marker}
## Dead Ends Registry (deadweight)

This project uses [deadweight]({base}) to track approaches that failed.

**Before trying a non-trivial approach**, query for known dead ends:

```bash
curl -s "{base}/query?repo={repo}&approach={{keywords}}"
```

If the `reason` field matches your situation, skip that approach entirely.

**When you abandon an approach after 3+ turns**, log it so the next agent doesn't repeat it:

```bash
curl -s -X POST {base}/log \\
  -H "Content-Type: application/json" \\
  -d '{{"repo":"{repo}","approach":"{{what you tried}}","reason":"{{why it failed}}","turns_wasted":{{N}}}}'
```
"""


def _detect_repo() -> str:
    """Detect repo identifier from git remote origin, fall back to directory name."""
    try:
        url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        # git@github.com:owner/repo.git  or  https://github.com/owner/repo.git
        m = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
        if m:
            return m.group(1)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return os.path.basename(os.getcwd())


def _inject(path: Path, section: str, label: str) -> bool:
    """Append section to file if the marker isn't already present. Returns True if written."""
    if path.exists():
        content = path.read_text()
        if _MARKER in content:
            print(f"  {path.name}: already has deadweight section, skipping")
            return False
        # Ensure trailing newline before appending
        if content and not content.endswith("\n"):
            content += "\n"
        content += "\n" + section
    else:
        content = f"# {label}\n\n" + section

    path.write_text(content)
    print(f"  {path.name}: added deadweight section")
    return True


def cmd_init(args: argparse.Namespace) -> None:
    """Add deadweight instructions to AGENTS.md and CLAUDE.md."""
    base = args.url.rstrip("/")
    repo = args.repo or _detect_repo()

    print(f"deadweight init — repo={repo} base={base}\n")

    root = Path.cwd()
    wrote_any = False

    agents_text = _AGENTS_SECTION.format(marker=_MARKER, base=base, repo=repo)
    wrote_any |= _inject(root / "AGENTS.md", agents_text, "Agent Instructions")

    claude_text = _CLAUDE_SECTION.format(marker=_MARKER, base=base, repo=repo)
    wrote_any |= _inject(root / "CLAUDE.md", claude_text, "Project Instructions")

    if wrote_any:
        print(f"\nDone. Agents entering this repo will now query deadweight automatically.")
    else:
        print(f"\nNothing to do — deadweight sections already present.")


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="deadweight",
        description="The dead ends registry — approaches your agent should never try again.",
    )
    sub = parser.add_subparsers(dest="command")

    # deadweight serve
    serve_p = sub.add_parser("serve", help="Start the deadweight server")
    serve_p.add_argument("--host", default="0.0.0.0")
    serve_p.add_argument("--port", type=int, default=8340)
    serve_p.add_argument("--reload", action="store_true")

    # deadweight init
    init_p = sub.add_parser(
        "init",
        help="Add deadweight instructions to AGENTS.md and CLAUDE.md",
    )
    init_p.add_argument(
        "--repo",
        default=None,
        help="Repository identifier (default: auto-detect from git remote)",
    )
    init_p.add_argument(
        "--url",
        default=DEFAULT_BASE_URL,
        help=f"Deadweight server URL (default: {DEFAULT_BASE_URL})",
    )

    args = parser.parse_args()

    if args.command == "serve":
        try:
            import uvicorn
        except ImportError:
            print("Install uvicorn: pip install 'deadweight[server]'", file=sys.stderr)
            sys.exit(1)
        uvicorn.run(
            "deadweight.server:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    elif args.command == "init":
        cmd_init(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
