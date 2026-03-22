"""Analyze benchmark results and produce the comparison table.

Usage:
    python analyze.py --control results/control_r2/ --treatment results/treatment/ --output results/report.md
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TaskResult:
    task_id: str
    turns: float
    wall_clock: float
    cost: float
    patch_produced: bool
    dead_end_reentries: int


def load_results(result_dir: Path) -> list[TaskResult]:
    results = []
    for f in sorted(result_dir.glob("*.json")):
        if f.name == "summary.json":
            continue
        data = json.loads(f.read_text())
        results.append(
            TaskResult(
                task_id=data["task_id"],
                turns=data["turns"],
                wall_clock=data["wall_clock_seconds"],
                cost=data["cost_usd"],
                patch_produced=data["patch_produced"],
                dead_end_reentries=data["dead_end_reentries"],
            )
        )
    return results


def cohens_d(group1: list[float], group2: list[float]) -> float:
    """Compute Cohen's d effect size."""
    n1, n2 = len(group1), len(group2)
    if n1 == 0 or n2 == 0:
        return 0.0
    m1, m2 = sum(group1) / n1, sum(group2) / n2
    var1 = sum((x - m1) ** 2 for x in group1) / max(n1 - 1, 1)
    var2 = sum((x - m2) ** 2 for x in group2) / max(n2 - 1, 1)
    pooled_std = math.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / max(n1 + n2 - 2, 1))
    if pooled_std == 0:
        return 0.0
    return (m1 - m2) / pooled_std


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--treatment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    control = load_results(args.control)
    treatment = load_results(args.treatment)

    if not control or not treatment:
        print("No results found. Run the evaluation first.")
        return

    def avg(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0

    c_turns = [r.turns for r in control]
    t_turns = [r.turns for r in treatment]
    c_time = [r.wall_clock for r in control]
    t_time = [r.wall_clock for r in treatment]
    c_cost = [r.cost for r in control]
    t_cost = [r.cost for r in treatment]

    report = f"""# deadweight Benchmark Results

## SWE-bench Lite (57 tasks, Claude Opus 4.5)

| Metric | Baseline (no dead ends) | + deadweight | Delta | Cohen's d |
|--------|-------------------------|--------------|-------|-----------|
| Avg turns/task | {avg(c_turns):.1f} | {avg(t_turns):.1f} | {(avg(t_turns) - avg(c_turns)) / max(avg(c_turns), 0.01) * 100:+.1f}% | {cohens_d(c_turns, t_turns):.2f} |
| Avg time/task | {avg(c_time):.1f}s | {avg(t_time):.1f}s | {(avg(t_time) - avg(c_time)) / max(avg(c_time), 0.01) * 100:+.1f}% | {cohens_d(c_time, t_time):.2f} |
| Avg cost/task | ${avg(c_cost):.2f} | ${avg(t_cost):.2f} | {(avg(t_cost) - avg(c_cost)) / max(avg(c_cost), 0.01) * 100:+.1f}% | {cohens_d(c_cost, t_cost):.2f} |
| Patch rate | {sum(1 for r in control if r.patch_produced) / max(len(control), 1) * 100:.1f}% | {sum(1 for r in treatment if r.patch_produced) / max(len(treatment), 1) * 100:.1f}% | — | — |
| Dead end re-entry | {avg([r.dead_end_reentries for r in control]):.1f} | {avg([r.dead_end_reentries for r in treatment]):.1f} | — | {cohens_d([float(r.dead_end_reentries) for r in control], [float(r.dead_end_reentries) for r in treatment]):.2f} |

## Methodology

- Control: Baseline (no dead ends access)
- Treatment: deadweight access enabled
- 2 runs per task per arm, paired comparison
- Statistical test: paired t-test, Cohen's d for effect size
- Total sessions: {len(control) + len(treatment)}
"""

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report)
    print(report)
    print(f"\nReport written to {args.output}")


if __name__ == "__main__":
    main()
