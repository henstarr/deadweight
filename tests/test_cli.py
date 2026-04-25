"""CLI + storage integration tests.

We shell out to the CLI via its module entry-point. This exercises the real
argparse + command wiring without requiring the package to be installed with
console scripts registered.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from deadweight.db import (
    DB_FILE,
    JSONL_FILE,
    STORE_DIRNAME,
    _FTS5_AVAILABLE,
    append_dead_end,
    find_store,
    get_dead_end,
    get_repo_insights,
    init_store,
    query_dead_ends,
    rebuild_index,
    update_dead_end,
)
from deadweight.models import DeadEndCreate


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    return subprocess.run(
        [sys.executable, "-m", "deadweight.cli", *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
    )


# ---------------------------------------------------------------------------
# Storage layer
# ---------------------------------------------------------------------------


def test_init_store_creates_layout(tmp_path: Path):
    store = init_store(tmp_path, repo="owner/repo")
    assert store == tmp_path / STORE_DIRNAME
    assert (store / JSONL_FILE).exists()
    assert (store / "config.yaml").exists()
    assert (store / ".gitignore").exists()
    assert "repo: owner/repo" in (store / "config.yaml").read_text()


def test_find_store_walks_up(tmp_path: Path):
    init_store(tmp_path, "owner/repo")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    found = find_store(nested)
    assert found == tmp_path / STORE_DIRNAME


def test_append_and_query(tmp_path: Path):
    store = init_store(tmp_path, "test/repo")
    de = append_dead_end(
        store,
        DeadEndCreate(
            repo="test/repo",
            approach="monkeypatching the thing",
            reason="breaks everything",
            turns_wasted=7,
            agent="claude-code",
        ),
    )
    assert de.id
    # jsonl has one line
    lines = (store / JSONL_FILE).read_text().strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["approach"] == "monkeypatching the thing"

    results = query_dead_ends(store, repo="test/repo")
    assert len(results) == 1
    assert results[0].approach == "monkeypatching the thing"


def test_query_approach_keyword_scoring(tmp_path: Path):
    store = init_store(tmp_path, "test/repo")
    append_dead_end(store, DeadEndCreate(repo="test/repo", approach="using raw SQL injection"))
    append_dead_end(store, DeadEndCreate(repo="test/repo", approach="subclassing the manager"))

    results = query_dead_ends(store, repo="test/repo", approach="raw SQL")
    assert len(results) == 1
    assert "raw SQL" in results[0].approach


def test_index_rebuild_from_jsonl(tmp_path: Path):
    store = init_store(tmp_path, "test/repo")
    append_dead_end(store, DeadEndCreate(repo="test/repo", approach="one"))
    append_dead_end(store, DeadEndCreate(repo="test/repo", approach="two"))

    # Nuke the db and confirm rebuild recovers both entries
    n = rebuild_index(store)
    assert n == 2
    results = query_dead_ends(store, repo="test/repo")
    assert len(results) == 2


def test_index_auto_rebuild_when_jsonl_newer(tmp_path: Path):
    store = init_store(tmp_path, "test/repo")
    append_dead_end(store, DeadEndCreate(repo="test/repo", approach="one"))

    # Simulate another clone appending to jsonl out-of-band
    with (store / JSONL_FILE).open("a") as f:
        f.write(json.dumps({
            "id": "abc123def456",
            "repo": "test/repo",
            "approach": "out-of-band append",
            "created_at": "2026-04-19T00:00:00+00:00",
        }) + "\n")
    # Bump mtime to make sure jsonl > db
    jsonl = store / JSONL_FILE
    os.utime(jsonl, (jsonl.stat().st_atime + 2, jsonl.stat().st_mtime + 2))

    results = query_dead_ends(store, repo="test/repo")
    assert len(results) == 2
    approaches = {r.approach for r in results}
    assert "out-of-band append" in approaches


def test_insights(tmp_path: Path):
    store = init_store(tmp_path, "insights/repo")
    for i in range(3):
        append_dead_end(
            store,
            DeadEndCreate(
                repo="insights/repo",
                approach="bad approach",
                reason="it fails",
                turns_wasted=5 + i,
            ),
        )

    insight = get_repo_insights(store, "insights/repo")
    assert insight is not None
    assert insight.total_dead_ends == 3
    assert insight.total_turns_wasted == 18  # 5+6+7


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_init(tmp_path: Path):
    r = _run(tmp_path, "init", "--repo", "owner/repo", "--no-hooks")
    assert r.returncode == 0, r.stderr
    assert (tmp_path / STORE_DIRNAME / JSONL_FILE).exists()
    assert "AGENTS.md" in r.stdout
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / "CLAUDE.md").exists()


def test_cli_init_installs_hooks(tmp_path: Path):
    r = _run(tmp_path, "init", "--repo", "owner/repo")
    assert r.returncode == 0, r.stderr
    settings = tmp_path / ".claude" / "settings.json"
    assert settings.exists()
    data = json.loads(settings.read_text())
    assert "SessionStart" in data["hooks"]
    assert "Stop" in data["hooks"]
    # Rerunning should be idempotent
    _run(tmp_path, "init", "--repo", "owner/repo")
    data2 = json.loads(settings.read_text())
    assert len(data2["hooks"]["Stop"]) == 1


def test_cli_log_and_query_round_trip(tmp_path: Path):
    _run(tmp_path, "init", "--repo", "test/repo", "--no-hooks")
    r = _run(
        tmp_path,
        "log",
        "--approach", "monkeypatching the thing",
        "--reason", "it breaks",
        "--turns-wasted", "7",
        "--agent", "claude-code",
        "--json",
    )
    assert r.returncode == 0, r.stderr
    log_out = json.loads(r.stdout)
    assert log_out["status"] == "logged"

    r = _run(tmp_path, "query", "--approach", "monkeypatching", "--json")
    assert r.returncode == 0, r.stderr
    q_out = json.loads(r.stdout)
    assert q_out["count"] == 1
    assert "monkeypatching" in q_out["dead_ends"][0]["approach"]


def test_cli_list_and_show(tmp_path: Path):
    _run(tmp_path, "init", "--repo", "test/repo", "--no-hooks")
    _run(tmp_path, "log", "--approach", "first")
    r = _run(tmp_path, "list", "--json")
    entries = json.loads(r.stdout)
    assert len(entries) == 1
    id_ = entries[0]["id"]

    r = _run(tmp_path, "show", id_)
    assert r.returncode == 0, r.stderr
    shown = json.loads(r.stdout)
    assert shown["id"] == id_


def test_cli_insights(tmp_path: Path):
    _run(tmp_path, "init", "--repo", "i/repo", "--no-hooks")
    for n in range(2):
        _run(
            tmp_path,
            "log",
            "--approach", "bad",
            "--reason", "it fails",
            "--turns-wasted", str(3 + n),
        )
    r = _run(tmp_path, "insights", "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["total_dead_ends"] == 2
    assert data["total_turns_wasted"] == 7


def test_cli_rebuild(tmp_path: Path):
    _run(tmp_path, "init", "--repo", "r/repo", "--no-hooks")
    _run(tmp_path, "log", "--approach", "something")
    # Delete db and rebuild
    (tmp_path / STORE_DIRNAME / DB_FILE).unlink()
    r = _run(tmp_path, "rebuild")
    assert r.returncode == 0, r.stderr
    assert "1 entries" in r.stdout


def test_cli_check_outside_store_is_silent(tmp_path: Path):
    r = _run(tmp_path, "check")
    assert r.returncode == 0
    assert r.stdout == ""


def test_cli_check_inside_store(tmp_path: Path):
    _run(tmp_path, "init", "--repo", "r/repo", "--no-hooks")
    r = _run(tmp_path, "check")
    assert r.returncode == 0
    assert "deadweight" in r.stdout
    assert "0 dead ends" in r.stdout


def test_cli_log_requires_init(tmp_path: Path):
    r = _run(tmp_path, "log", "--approach", "x")
    assert r.returncode == 2
    assert "No .deadweight/" in r.stderr


def test_cli_log_invalid_agent_fails(tmp_path: Path):
    _run(tmp_path, "init", "--repo", "r/repo", "--no-hooks")
    r = _run(tmp_path, "log", "--approach", "x", "--agent", "bogus-agent")
    assert r.returncode != 0


# ---------------------------------------------------------------------------
# FTS5 search quality
# ---------------------------------------------------------------------------


def test_fts_searches_reason_field(tmp_path: Path):
    """FTS5 should match keywords in reason, not just approach."""
    store = init_store(tmp_path, "test/repo")
    append_dead_end(
        store,
        DeadEndCreate(
            repo="test/repo",
            approach="patching the internal cache",
            reason="causes deadlock under concurrent writes",
        ),
    )
    append_dead_end(
        store,
        DeadEndCreate(repo="test/repo", approach="subclassing the manager"),
    )

    results = query_dead_ends(store, repo="test/repo", approach="deadlock")
    assert len(results) >= 1
    assert any("cache" in r.approach for r in results)


def test_fts_ranks_closer_matches_higher(tmp_path: Path):
    """Entry matching more keywords should rank above entry matching fewer."""
    store = init_store(tmp_path, "test/repo")
    append_dead_end(
        store, DeadEndCreate(repo="test/repo", approach="raw SQL query injection bypass")
    )
    append_dead_end(
        store, DeadEndCreate(repo="test/repo", approach="raw filesystem access")
    )

    if not _FTS5_AVAILABLE:
        return  # skip ranking check without FTS5

    results = query_dead_ends(store, repo="test/repo", approach="raw SQL query")
    assert len(results) >= 1
    assert "SQL" in results[0].approach


def test_fts_filters_resolved_by_default(tmp_path: Path):
    """Resolved dead ends should not appear in query results by default."""
    store = init_store(tmp_path, "test/repo")
    de = append_dead_end(
        store, DeadEndCreate(repo="test/repo", approach="using raw SQL injection")
    )
    update_dead_end(store, de.id)

    results = query_dead_ends(store, repo="test/repo", approach="raw SQL")
    assert all(r.id != de.id for r in results)


def test_fts_include_resolved_flag(tmp_path: Path):
    """include_resolved=True should surface resolved entries."""
    store = init_store(tmp_path, "test/repo")
    de = append_dead_end(
        store, DeadEndCreate(repo="test/repo", approach="using raw SQL injection")
    )
    update_dead_end(store, de.id)

    results = query_dead_ends(store, repo="test/repo", approach="raw SQL", include_resolved=True)
    assert any(r.id == de.id for r in results)


# ---------------------------------------------------------------------------
# dw update --resolved
# ---------------------------------------------------------------------------


def test_update_resolved_storage(tmp_path: Path):
    """Resolving a dead end marks it in SQLite and appends a delta to jsonl."""
    store = init_store(tmp_path, "test/repo")
    de = append_dead_end(
        store, DeadEndCreate(repo="test/repo", approach="bad thing")
    )

    result = update_dead_end(store, de.id)
    assert result is not None
    assert result.resolved is True
    assert result.resolved_at is not None

    # SQLite reflects the resolution
    fetched = get_dead_end(store, de.id)
    assert fetched is not None
    assert fetched.resolved is True

    # JSONL contains a delta line
    lines = [json.loads(l) for l in (store / JSONL_FILE).read_text().splitlines() if l.strip()]
    delta_lines = [l for l in lines if l.get("_resolved")]
    assert len(delta_lines) == 1
    assert delta_lines[0]["id"] == de.id


def test_update_resolved_survives_rebuild(tmp_path: Path):
    """Resolution delta is replayed correctly on full index rebuild."""
    store = init_store(tmp_path, "test/repo")
    de = append_dead_end(
        store, DeadEndCreate(repo="test/repo", approach="bad thing")
    )
    update_dead_end(store, de.id)

    rebuild_index(store)

    fetched = get_dead_end(store, de.id)
    assert fetched is not None
    assert fetched.resolved is True

    # Should not appear in default queries
    results = query_dead_ends(store, repo="test/repo")
    assert all(r.id != de.id for r in results)


def test_cli_update_resolved(tmp_path: Path):
    """CLI: dw update <id> --resolved marks the dead end as resolved."""
    _run(tmp_path, "init", "--repo", "r/repo", "--no-hooks")
    r = _run(tmp_path, "log", "--approach", "bad pattern", "--json")
    assert r.returncode == 0
    id_ = json.loads(r.stdout)["id"]

    r = _run(tmp_path, "update", id_, "--resolved")
    assert r.returncode == 0
    assert "resolved" in r.stdout

    # Should no longer appear in list
    r = _run(tmp_path, "list", "--json")
    entries = json.loads(r.stdout)
    assert all(e["id"] != id_ for e in entries)


def test_cli_update_missing_id_fails(tmp_path: Path):
    _run(tmp_path, "init", "--repo", "r/repo", "--no-hooks")
    r = _run(tmp_path, "update", "nonexistentid", "--resolved")
    assert r.returncode == 1


# ---------------------------------------------------------------------------
# Grammar
# ---------------------------------------------------------------------------


def test_check_singular_grammar(tmp_path: Path):
    """'1 dead end' should use singular, not '1 dead ends'."""
    _run(tmp_path, "init", "--repo", "r/repo", "--no-hooks")
    _run(tmp_path, "log", "--approach", "only one")
    r = _run(tmp_path, "check", "--session-start")
    assert "1 dead end" in r.stdout
    assert "1 dead ends" not in r.stdout
