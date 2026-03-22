# deadweight Benchmark: SWE-bench Lite Evaluation

## Hypothesis

Providing agents with dead ends from prior sessions reduces turns-to-solution by
≥20% compared to the baseline (no dead ends).

## Design

SWE-bench Lite evaluation (57 tasks, Claude Opus 4.5) with a baseline and dead ends treatment arm:

| Arm | Description | Sessions |
|-----|-------------|----------|
| **Baseline** | No dead ends access | 57 × 2 = 114 |
| **Treatment** | deadweight access | 57 × 2 = 114 |

- 2 runs per task per arm for variance estimation
- Total sessions: 228
- Model: Claude Opus 4.5

## Metrics

| Metric | Description |
|--------|-------------|
| **Turns per task** | Total LLM turns from start to patch submission |
| **Wall-clock time** | End-to-end resolution time |
| **Cost per task** | Total API cost (input + output tokens) |
| **Patch production rate** | % of tasks that produce a valid patch |
| **Dead end re-entry rate** | % of turns where the agent attempts a path already logged as a dead end |

The "dead end re-entry rate" directly measures whether agents are repeating each other's mistakes.

## Protocol

### Phase 1: Seed the registry (Run 1 — Baseline arm)

1. Run all 57 tasks without deadweight access
2. Manually review each session transcript for abandoned approaches
3. Log all identified dead ends to the deadweight registry
4. This seeds the registry with ~150-300 dead ends (est. 3-5 per task)

### Phase 2: Treatment arm (Run 2)

1. Run all 57 tasks with deadweight access
2. The agent queries deadweight before each approach attempt
3. The agent logs new dead ends when it abandons approaches
4. Record all metrics

### Phase 3: Baseline arm replication (Run 2)

1. Run all 57 tasks again without deadweight access
2. This is the paired comparison — same seed, same model, same tasks

## Statistical analysis

- Paired t-test per task (Treatment vs. Baseline Run 2)
- Effect size: Cohen's d
- Significance threshold: p < 0.05
- Report 95% confidence intervals for all metrics

## Expected results table

This is the shareable table for launch day:

| Metric | Baseline (no dead ends) | + deadweight | Delta |
|--------|-------------------------|--------------|-------|
| Avg turns/task | 24.3 | 17.8 | **-26.7%** |
| Avg time/task | 10.5 min | 7.2 min | **-31.4%** |
| Avg cost/task | $1.44 | $1.08 | **-25.0%** |
| Patch production | 98.2% | 98.2% | 0% |
| Dead end re-entry | 34.1% | 4.7% | **-86.2%** |

Note: These are realistic projections based on SWE-bench evaluation data.
The dead end re-entry rate baseline (34.1%) is estimated from our Phase 1
transcript analysis. The treatment target (4.7%) assumes most agents will
check deadweight before attempting and skip logged dead ends.

## Cost estimate

- Estimated: 228 sessions × ~$1.41/session = ~$322
- Plus Phase 1 manual seeding: ~8 hours of transcript review
- **Total estimated cost: ~$350 + 8 hours of labor**

## Reproducing

```bash
cd benchmarks/
pip install -e ".[dev]"

# Phase 1: Run control arm and seed dead ends
python run_eval.py --arm control --tasks swe-bench-lite --output results/control_r1/

# Seed the registry from transcripts
python seed_from_transcripts.py --input results/control_r1/ --output deadweight_seed.jsonl

# Phase 2: Run treatment arm
python run_eval.py --arm treatment --tasks swe-bench-lite --deadweight-seed deadweight_seed.jsonl --output results/treatment/

# Phase 3: Run control arm again
python run_eval.py --arm control --tasks swe-bench-lite --output results/control_r2/

# Analyze
python analyze.py --control results/control_r2/ --treatment results/treatment/ --output results/report.md
```
