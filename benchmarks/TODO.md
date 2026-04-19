# Benchmarks — TODO after CLI transition

The SWE-bench eval harness in `run_eval.py`, `analyze.py`, and `seed_from_transcripts.py`
was written against the hosted-service API (`POST /log`, `GET /query`, `GET /insights`).
Those endpoints are gone. The benchmarks need to be rewritten to drive the CLI:

- `seed_from_transcripts.py` → `dw log` per transcript line
- `run_eval.py` → agent loop shells out to `dw query` / `dw log`
- `analyze.py` → `dw insights --json` instead of an HTTP call

Numbers in the old README (26% fewer turns, 31% less wall-clock, 25% cheaper, dead-end
re-entry rate 34% → 5%) came from the hosted-service run and should not be quoted until
the CLI version is re-run end-to-end.
