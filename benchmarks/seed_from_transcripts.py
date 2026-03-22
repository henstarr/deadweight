"""Extract dead ends from SWE-bench session transcripts.

Reads agent session transcripts from the control arm and identifies
abandoned approaches to seed the deadweight registry.

Usage:
    python seed_from_transcripts.py --input results/control_r1/ --output deadweight_seed.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def extract_dead_ends(transcript_path: Path) -> list[dict]:
    """Extract dead ends from a session transcript.

    TODO: Implement transcript parsing.

    Heuristics for identifying dead ends in a transcript:
    1. Agent says "let me try X" followed later by "that doesn't work" / "reverting"
    2. Agent edits a file, then reverts the edit within 5 turns
    3. Agent searches for a function/file, spends 3+ turns exploring it, then moves on
    4. Agent explicitly says "this approach won't work because..."

    Each extracted dead end should include:
    - approach: what was tried (extracted from agent's stated intent)
    - reason: why it was abandoned (extracted from agent's explanation)
    - turns_wasted: number of turns between starting and abandoning
    - path: file(s) involved
    """
    # Placeholder — this is the manual review step in Phase 1
    return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    all_dead_ends = []

    for transcript_file in sorted(args.input.glob("*.json")):
        data = json.loads(transcript_file.read_text())
        task_id = data.get("task_id", transcript_file.stem)
        dead_ends = extract_dead_ends(transcript_file)

        for de in dead_ends:
            de["task_id"] = task_id
            all_dead_ends.append(de)

    with open(args.output, "w") as f:
        for de in all_dead_ends:
            f.write(json.dumps(de) + "\n")

    print(f"Extracted {len(all_dead_ends)} dead ends → {args.output}")


if __name__ == "__main__":
    main()
