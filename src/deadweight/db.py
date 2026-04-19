"""Repo-local storage layer for .deadweight/.

Layout (mirrors beads):
    .deadweight/
      deadends.jsonl   — source of truth, committed to git
      deadends.db      — SQLite index, rebuildable, gitignored
      config.yaml      — repo id, sync branch

The JSONL is authoritative. The SQLite DB is a cache built from it. If the JSONL
is newer than the DB, we rebuild on next access. All writes append to the JSONL
first, then insert into the index.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from .models import (
    DeadEnd,
    DeadEndCreate,
    DeadEndSummary,
    PathSummary,
    RepoInsight,
)

logger = logging.getLogger("deadweight.db")

STORE_DIRNAME = ".deadweight"
JSONL_FILE = "deadends.jsonl"
DB_FILE = "deadends.db"
CONFIG_FILE = "config.yaml"
GITIGNORE_FILE = ".gitignore"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS dead_ends (
    id TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    path TEXT,
    approach TEXT NOT NULL,
    reason TEXT,
    turns_wasted INTEGER,
    agent TEXT,
    version TEXT,
    task_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_repo ON dead_ends(repo);
CREATE INDEX IF NOT EXISTS idx_repo_path ON dead_ends(repo, path);
CREATE INDEX IF NOT EXISTS idx_approach ON dead_ends(approach);
CREATE INDEX IF NOT EXISTS idx_created_at ON dead_ends(created_at);
"""


# ---------------------------------------------------------------------------
# Store discovery
# ---------------------------------------------------------------------------


def find_store(start: Path | None = None) -> Path | None:
    """Walk up from `start` (or cwd) looking for a `.deadweight/` directory."""
    p = (start or Path.cwd()).resolve()
    for cand in [p, *p.parents]:
        candidate = cand / STORE_DIRNAME
        if candidate.is_dir():
            return candidate
    return None


def require_store(start: Path | None = None) -> Path:
    store = find_store(start)
    if store is None:
        raise RuntimeError(
            "No .deadweight/ directory found. Run `deadweight init` in your repo first."
        )
    return store


def init_store(root: Path, repo: str) -> Path:
    """Create `.deadweight/` under `root`, idempotent."""
    store = root / STORE_DIRNAME
    store.mkdir(exist_ok=True)

    jsonl = store / JSONL_FILE
    if not jsonl.exists():
        jsonl.write_text("")

    cfg = store / CONFIG_FILE
    if not cfg.exists():
        cfg.write_text(
            "# deadweight config — committed to git so all clones agree\n"
            f"repo: {repo}\n"
            "schema_version: 1\n"
            "sync_branch: deadweight-sync\n"
        )

    gi = store / GITIGNORE_FILE
    if not gi.exists():
        gi.write_text(
            "# Local SQLite index — rebuildable from deadends.jsonl\n"
            "*.db\n"
            "*.db-*\n"
        )

    return store


def read_config(store: Path) -> dict:
    """Minimal `key: value` parser. Ignores comments, blank lines."""
    cfg: dict = {}
    path = store / CONFIG_FILE
    if not path.exists():
        return cfg
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, _, value = stripped.partition(":")
        if key:
            cfg[key.strip()] = value.strip()
    return cfg


# ---------------------------------------------------------------------------
# Connection / index rebuild
# ---------------------------------------------------------------------------


def _db_path(store: Path) -> Path:
    return store / DB_FILE


def _jsonl_path(store: Path) -> Path:
    return store / JSONL_FILE


def _needs_rebuild(store: Path) -> bool:
    db = _db_path(store)
    jsonl = _jsonl_path(store)
    if not db.exists():
        return jsonl.exists()
    if not jsonl.exists():
        return False
    return jsonl.stat().st_mtime > db.stat().st_mtime


def _open(store: Path) -> sqlite3.Connection:
    """Open a connection, rebuilding the index if the jsonl is newer."""
    db = _db_path(store)
    rebuild = _needs_rebuild(store)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA_SQL)
    if rebuild:
        _rebuild_from_jsonl(conn, _jsonl_path(store))
    return conn


def _rebuild_from_jsonl(conn: sqlite3.Connection, jsonl: Path) -> int:
    conn.execute("DELETE FROM dead_ends")
    count = 0
    if jsonl.exists():
        for line in jsonl.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed jsonl line: %.80s", line)
                continue
            _insert_row(conn, data)
            count += 1
    conn.commit()
    return count


def rebuild_index(store: Path) -> int:
    """Force full rebuild of the sqlite index from the jsonl."""
    db = _db_path(store)
    for side in (db, db.parent / (db.name + "-wal"), db.parent / (db.name + "-shm")):
        if side.exists():
            side.unlink()
    conn = _open(store)
    try:
        n = conn.execute("SELECT COUNT(*) FROM dead_ends").fetchone()[0]
    finally:
        conn.close()
    return n


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def _insert_row(conn: sqlite3.Connection, data: dict) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO dead_ends
           (id, repo, path, approach, reason, turns_wasted, agent, version, task_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("id"),
            data.get("repo"),
            data.get("path"),
            data.get("approach"),
            data.get("reason"),
            data.get("turns_wasted"),
            data.get("agent"),
            data.get("version"),
            data.get("task_id"),
            data.get("created_at"),
        ),
    )


def append_dead_end(store: Path, entry: DeadEndCreate) -> DeadEnd:
    """Append an entry to the jsonl and insert into the index."""
    dead_end = DeadEnd(**entry.model_dump())
    row = dead_end.model_dump()
    row["created_at"] = dead_end.created_at.isoformat()
    row["agent"] = dead_end.agent.value if dead_end.agent else None

    jsonl_row = {k: v for k, v in row.items() if v is not None}
    jsonl_row.pop("relevance_score", None)

    with _jsonl_path(store).open("a", encoding="utf-8") as f:
        f.write(json.dumps(jsonl_row, ensure_ascii=False) + "\n")

    conn = _open(store)
    try:
        _insert_row(conn, row)
        conn.commit()
    finally:
        conn.close()
    return dead_end


def _row_to_dead_end(row: dict) -> DeadEnd:
    created = row["created_at"]
    if isinstance(created, str):
        created = datetime.fromisoformat(created)
    return DeadEnd(
        id=row["id"],
        repo=row["repo"],
        path=row.get("path"),
        approach=row["approach"],
        reason=row.get("reason"),
        turns_wasted=row.get("turns_wasted"),
        agent=row.get("agent"),
        version=row.get("version"),
        task_id=row.get("task_id"),
        created_at=created,
    )


def query_dead_ends(
    store: Path,
    repo: str | None = None,
    path: str | None = None,
    approach: str | None = None,
    agent: str | None = None,
    limit: int = 10,
) -> list[DeadEnd]:
    clauses: list[str] = []
    params: list = []
    if repo:
        clauses.append("repo = ?")
        params.append(repo)
    if path:
        clauses.append("path LIKE ?")
        params.append(f"{path}%")
    if agent:
        clauses.append("agent = ?")
        params.append(agent)

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM dead_ends{where} ORDER BY created_at DESC"

    conn = _open(store)
    try:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()

    results = [_row_to_dead_end(r) for r in rows]

    if approach:
        keywords = approach.lower().split()
        scored = []
        for de in results:
            text = de.approach.lower()
            hits = sum(1 for kw in keywords if kw in text)
            if hits > 0:
                de.relevance_score = hits / len(keywords)
                scored.append(de)
        scored.sort(key=lambda d: d.relevance_score or 0, reverse=True)
        return scored[:limit]

    return results[:limit]


def get_dead_end(store: Path, id_: str) -> DeadEnd | None:
    conn = _open(store)
    try:
        row = conn.execute("SELECT * FROM dead_ends WHERE id = ?", (id_,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return _row_to_dead_end(dict(row))


def recent_dead_ends(store: Path, limit: int = 10) -> list[DeadEnd]:
    return query_dead_ends(store, limit=limit)


def get_repo_insights(store: Path, repo: str) -> RepoInsight | None:
    conn = _open(store)
    try:
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM dead_ends WHERE repo = ?", (repo,)
        ).fetchone()
        if not total or total["cnt"] == 0:
            return None

        total_turns = conn.execute(
            "SELECT COALESCE(SUM(turns_wasted), 0) as s FROM dead_ends WHERE repo = ?",
            (repo,),
        ).fetchone()

        avg_turns = conn.execute(
            "SELECT COALESCE(AVG(turns_wasted), 0) as a FROM dead_ends "
            "WHERE repo = ? AND turns_wasted IS NOT NULL",
            (repo,),
        ).fetchone()

        top_rows = conn.execute(
            """SELECT approach, reason, COUNT(*) as occ,
                      COALESCE(SUM(turns_wasted), 0) as tw,
                      GROUP_CONCAT(DISTINCT path) as paths
               FROM dead_ends WHERE repo = ?
               GROUP BY LOWER(approach), approach, reason
               ORDER BY occ DESC, tw DESC
               LIMIT 10""",
            (repo,),
        ).fetchall()

        top_dead_ends = [
            DeadEndSummary(
                approach=r["approach"],
                reason=r["reason"],
                occurrences=r["occ"],
                total_turns_wasted=r["tw"],
                paths=[p for p in (r["paths"] or "").split(",") if p],
            )
            for r in top_rows
        ]

        path_rows = conn.execute(
            """SELECT path, COUNT(*) as cnt, COALESCE(SUM(turns_wasted), 0) as tw
               FROM dead_ends WHERE repo = ? AND path IS NOT NULL
               GROUP BY path ORDER BY cnt DESC LIMIT 10""",
            (repo,),
        ).fetchall()

        paths = [
            PathSummary(path=r["path"], dead_end_count=r["cnt"], total_turns_wasted=r["tw"])
            for r in path_rows
        ]

        agent_rows = conn.execute(
            """SELECT COALESCE(agent, 'unknown') as a, COUNT(*) as cnt
               FROM dead_ends WHERE repo = ? GROUP BY COALESCE(agent, 'unknown')""",
            (repo,),
        ).fetchall()

        agents = {r["a"]: r["cnt"] for r in agent_rows}

        return RepoInsight(
            repo=repo,
            total_dead_ends=total["cnt"],
            total_turns_wasted=total_turns["s"],
            avg_turns_per_dead_end=round(float(avg_turns["a"]), 1),
            top_dead_ends=top_dead_ends,
            most_common_paths=paths,
            agent_breakdown=agents,
        )
    finally:
        conn.close()
