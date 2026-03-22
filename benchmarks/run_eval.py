"""SWE-bench Lite evaluation harness for deadweight.

Evaluates the impact of dead ends on agent performance.

Usage:
    python run_eval.py --arm control --tasks swe-bench-lite --output results/control/
    python run_eval.py --arm treatment --tasks swe-bench-lite --deadweight-seed seed.jsonl --output results/treatment/
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SessionMetrics:
    task_id: str
    arm: str
    turns: int = 0
    wall_clock_seconds: float = 0.0
    cost_usd: float = 0.0
    patch_produced: bool = False
    dead_end_reentries: int = 0
    dead_ends_checked: int = 0
    dead_ends_logged: int = 0


def main() -> None:
    parser = argparse.ArgumentParser(description="deadweight SWE-bench evaluation")
    parser.add_argument("--arm", choices=["control", "treatment"], required=True)
    parser.add_argument("--tasks", default="swe-bench-lite")
    parser.add_argument("--deadweight-seed", type=Path, default=None)
    parser.add_argument("--deadweight-url", default="http://localhost:8340")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs-per-task", type=int, default=2)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    # Load SWE-bench Lite task IDs
    tasks = load_tasks(args.tasks)
    print(f"Loaded {len(tasks)} tasks from {args.tasks}")

    # Seed deadweight if treatment arm
    if args.arm == "treatment" and args.deadweight_seed:
        seed_deadweight(args.deadweight_seed, args.deadweight_url)

    results: list[SessionMetrics] = []

    for task_id in tasks:
        for run in range(args.runs_per_task):
            print(f"[{args.arm}] Task {task_id} run {run + 1}/{args.runs_per_task}")
            metrics = run_task(
                task_id=task_id,
                arm=args.arm,
                deadweight_url=args.deadweight_url if args.arm == "treatment" else None,
            )
            results.append(metrics)

            # Save incrementally
            out_file = args.output / f"{task_id}_run{run + 1}.json"
            out_file.write_text(json.dumps(metrics.__dict__, indent=2))

    # Write summary
    summary = compute_summary(results)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nDone. Results in {args.output}")
    print_summary(summary)


def load_tasks(task_set: str) -> list[str]:
    """Load SWE-bench Lite task IDs."""
    # TODO: Load from swe-bench dataset
    # For now, return placeholder
    print(f"TODO: Load {task_set} tasks from HuggingFace datasets")
    return []


def seed_deadweight(seed_file: Path, url: str) -> None:
    """Seed the deadweight registry from a JSONL file."""
    import httpx

    count = 0
    with open(seed_file) as f:
        for line in f:
            entry = json.loads(line)
            r = httpx.post(f"{url}/log", json=entry)
            if r.status_code == 201:
                count += 1
    print(f"Seeded {count} dead ends from {seed_file}")


def run_task(
    task_id: str,
    arm: str,
    deadweight_url: str | None = None,
) -> SessionMetrics:
    """Run a single SWE-bench task and collect metrics.

    TODO: Integrate with actual SWE-bench harness and Claude API.
    This is the scaffold — the integration points are marked.
    """
    metrics = SessionMetrics(task_id=task_id, arm=arm)

    # TODO: Implementation
    # 1. Set up the SWE-bench task environment
    # 2. Configure the agent with/without deadweight access
    # 3. Run the agent
    # 4. Collect metrics from the session transcript
    # 5. Check patch validity

    return metrics


def compute_summary(results: list[SessionMetrics]) -> dict:
    if not results:
        return {}

    n = len(results)
    return {
        "total_sessions": n,
        "avg_turns": sum(r.turns for r in results) / n,
        "avg_wall_clock": sum(r.wall_clock_seconds for r in results) / n,
        "avg_cost": sum(r.cost_usd for r in results) / n,
        "patch_rate": sum(1 for r in results if r.patch_produced) / n,
        "avg_dead_end_reentries": sum(r.dead_end_reentries for r in results) / n,
    }


def print_summary(summary: dict) -> None:
    if not summary:
        print("No results to summarize.")
        return
    print(f"\n{'='*50}")
    print(f"Sessions:           {summary['total_sessions']}")
    print(f"Avg turns/task:     {summary['avg_turns']:.1f}")
    print(f"Avg time/task:      {summary['avg_wall_clock']:.1f}s")
    print(f"Avg cost/task:      ${summary['avg_cost']:.2f}")
    print(f"Patch rate:         {summary['patch_rate']*100:.1f}%")
    print(f"Dead end reentries: {summary['avg_dead_end_reentries']:.1f}")


if __name__ == "__main__":
    main()
