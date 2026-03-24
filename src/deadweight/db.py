"""Database layer — SQLite for local dev, Postgres for production.

Selection is automatic: set DATABASE_URL for Postgres, otherwise SQLite.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator, Optional

logger = logging.getLogger("deadweight.db")

from .models import (
    AgentType,
    DeadEnd,
    DeadEndCreate,
    DeadEndSummary,
    PathSummary,
    RepoInsight,
    SimilarPattern,
)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SQLITE_PATH = os.environ.get("DEADWEIGHT_DB", "deadweight.db")

# Shared connection for in-memory databases (testing)
_shared_conn: Optional[sqlite3.Connection] = None

_USE_POSTGRES = bool(DATABASE_URL)

# ---------------------------------------------------------------------------
# Unified query helpers — paramstyle adapters
# ---------------------------------------------------------------------------
# SQLite uses ? placeholders, Postgres uses %s.
# We write queries with ? and convert at execution time for Postgres.


def _pg_sql(sql: str) -> str:
    """Convert ? placeholders to %s for psycopg2."""
    return sql.replace("?", "%s")


# ---------------------------------------------------------------------------
# Connection layer
# ---------------------------------------------------------------------------

SCHEMA_SQL_SQLITE = """
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
CREATE INDEX IF NOT EXISTS idx_repo_created_at ON dead_ends(repo, created_at);
"""

SCHEMA_SQL_PG = """
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
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_repo ON dead_ends(repo);
CREATE INDEX IF NOT EXISTS idx_repo_path ON dead_ends(repo, path);
CREATE INDEX IF NOT EXISTS idx_approach ON dead_ends(approach);
CREATE INDEX IF NOT EXISTS idx_created_at ON dead_ends(created_at);
CREATE INDEX IF NOT EXISTS idx_repo_created_at ON dead_ends(repo, created_at);
"""


def _init_pg() -> None:
    """Create tables in Postgres if they don't exist."""
    import psycopg2

    conn = psycopg2.connect(DATABASE_URL)
    try:
        cur = conn.cursor()
        cur.execute(SCHEMA_SQL_PG)
        conn.commit()
        cur.close()
    finally:
        conn.close()


_pg_initialized = False


@contextmanager
def _conn() -> Generator[Any, None, None]:
    """Yield a DB connection. SQLite or Postgres based on DATABASE_URL."""
    global _pg_initialized

    if _USE_POSTGRES:
        import psycopg2
        import psycopg2.extras

        if not _pg_initialized:
            _init_pg()
            _pg_initialized = True

        conn = psycopg2.connect(DATABASE_URL)
        try:
            conn.cursor_factory = psycopg2.extras.RealDictCursor
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            logger.error("Postgres transaction rolled back", exc_info=True)
            raise
        finally:
            conn.close()
    else:
        conn = _get_sqlite()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            logger.error("SQLite transaction rolled back", exc_info=True)
            raise
        finally:
            if SQLITE_PATH != ":memory:":
                conn.close()


def _get_sqlite() -> sqlite3.Connection:
    global _shared_conn
    if SQLITE_PATH == ":memory:":
        if _shared_conn is None:
            _shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            _shared_conn.row_factory = sqlite3.Row
            _shared_conn.executescript(SCHEMA_SQL_SQLITE)
        return _shared_conn
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA_SQL_SQLITE)
    return conn


def _execute(conn: Any, sql: str, params: tuple | list = ()) -> Any:
    """Execute a query, adapting placeholders for the active backend."""
    if _USE_POSTGRES:
        cur = conn.cursor()
        cur.execute(_pg_sql(sql), params)
        return cur
    else:
        return conn.execute(sql, params)


def _fetchone(conn: Any, sql: str, params: tuple | list = ()) -> Optional[dict]:
    cur = _execute(conn, sql, params)
    row = cur.fetchone()
    if row is None:
        return None
    return dict(row)


def _fetchall(conn: Any, sql: str, params: tuple | list = ()) -> list[dict]:
    cur = _execute(conn, sql, params)
    return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_repos(limit: int = 20) -> list[dict]:
    """List repos with dead end counts, ordered by count descending."""
    with _conn() as conn:
        rows = _fetchall(
            conn,
            "SELECT repo, COUNT(*) as count FROM dead_ends GROUP BY repo ORDER BY count DESC LIMIT ?",
            (limit,),
        )
    return [{"repo": r["repo"], "count": r["count"]} for r in rows]


def recent_dead_ends(limit: int = 10) -> list[DeadEnd]:
    """Get the most recent dead ends across all repos."""
    with _conn() as conn:
        rows = _fetchall(
            conn,
            "SELECT * FROM dead_ends ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
    return [_row_to_dead_end(r) for r in rows]


def insert_dead_end(entry: DeadEndCreate) -> DeadEnd:
    dead_end = DeadEnd(**entry.model_dump())
    created_at_val = dead_end.created_at.isoformat() if not _USE_POSTGRES else dead_end.created_at

    with _conn() as conn:
        _execute(
            conn,
            """INSERT INTO dead_ends
               (id, repo, path, approach, reason, turns_wasted, agent, version, task_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                dead_end.id,
                dead_end.repo,
                dead_end.path,
                dead_end.approach,
                dead_end.reason,
                dead_end.turns_wasted,
                dead_end.agent.value if dead_end.agent else None,
                dead_end.version,
                dead_end.task_id,
                created_at_val,
            ),
        )
    return dead_end


def query_dead_ends(
    repo: str,
    path: Optional[str] = None,
    approach: Optional[str] = None,
    agent: Optional[str] = None,
    limit: int = 10,
) -> list[DeadEnd]:
    clauses = ["repo = ?"]
    params: list = [repo]

    if path:
        clauses.append("path LIKE ?")
        params.append(f"{path}%")

    if agent:
        clauses.append("agent = ?")
        params.append(agent)

    where = " AND ".join(clauses)
    sql = f"SELECT * FROM dead_ends WHERE {where} ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with _conn() as conn:
        rows = _fetchall(conn, sql, params)

    results = [_row_to_dead_end(r) for r in rows]

    # Client-side keyword filtering on approach (simple but effective for v0.1)
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

    return results


def find_similar_patterns(
    approach: str, exclude_repo: Optional[str] = None, limit: int = 5
) -> list[SimilarPattern]:
    """Find dead ends from other repos with similar approach text."""
    keywords = approach.lower().split()
    if not keywords:
        return []

    with _conn() as conn:
        if exclude_repo:
            rows = _fetchall(
                conn,
                "SELECT repo, approach, reason, turns_wasted FROM dead_ends WHERE repo != ? ORDER BY created_at DESC LIMIT 500",
                (exclude_repo,),
            )
        else:
            rows = _fetchall(
                conn,
                "SELECT repo, approach, reason, turns_wasted FROM dead_ends ORDER BY created_at DESC LIMIT 500",
            )

    scored = []
    for r in rows:
        text = r["approach"].lower()
        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            scored.append(
                (
                    hits / len(keywords),
                    SimilarPattern(
                        repo=r["repo"],
                        approach=r["approach"],
                        reason=r["reason"],
                        turns_wasted=r["turns_wasted"],
                    ),
                )
            )

    scored.sort(key=lambda x: x[0], reverse=True)
    return [sp for _, sp in scored[:limit]]


def get_repo_insights(repo: str) -> Optional[RepoInsight]:
    # Postgres uses STRING_AGG, SQLite uses GROUP_CONCAT
    group_concat_fn = "STRING_AGG(DISTINCT path, ',')" if _USE_POSTGRES else "GROUP_CONCAT(DISTINCT path)"

    with _conn() as conn:
        total = _fetchone(
            conn, "SELECT COUNT(*) as cnt FROM dead_ends WHERE repo = ?", (repo,)
        )

        if not total or total["cnt"] == 0:
            return None

        total_turns = _fetchone(
            conn,
            "SELECT COALESCE(SUM(turns_wasted), 0) as s FROM dead_ends WHERE repo = ?",
            (repo,),
        )

        avg_turns = _fetchone(
            conn,
            "SELECT COALESCE(AVG(turns_wasted), 0) as a FROM dead_ends WHERE repo = ? AND turns_wasted IS NOT NULL",
            (repo,),
        )

        top_rows = _fetchall(
            conn,
            f"""SELECT approach, reason, COUNT(*) as occ,
                      COALESCE(SUM(turns_wasted), 0) as tw,
                      {group_concat_fn} as paths
               FROM dead_ends WHERE repo = ?
               GROUP BY LOWER(approach), approach, reason
               ORDER BY occ DESC, tw DESC
               LIMIT 10""",
            (repo,),
        )

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

        path_rows = _fetchall(
            conn,
            """SELECT path, COUNT(*) as cnt, COALESCE(SUM(turns_wasted), 0) as tw
               FROM dead_ends WHERE repo = ? AND path IS NOT NULL
               GROUP BY path ORDER BY cnt DESC LIMIT 10""",
            (repo,),
        )

        paths = [
            PathSummary(
                path=r["path"], dead_end_count=r["cnt"], total_turns_wasted=r["tw"]
            )
            for r in path_rows
        ]

        agent_rows = _fetchall(
            conn,
            """SELECT COALESCE(agent, 'unknown') as a, COUNT(*) as cnt
               FROM dead_ends WHERE repo = ? GROUP BY COALESCE(agent, 'unknown')""",
            (repo,),
        )

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


def _row_to_dead_end(row: dict) -> DeadEnd:
    created = row["created_at"]
    if isinstance(created, str):
        created = datetime.fromisoformat(created)
    return DeadEnd(
        id=row["id"],
        repo=row["repo"],
        path=row["path"],
        approach=row["approach"],
        reason=row["reason"],
        turns_wasted=row["turns_wasted"],
        agent=row["agent"],
        version=row["version"],
        task_id=row["task_id"],
        created_at=created,
    )
