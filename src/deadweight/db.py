"""Repo-local storage layer for .deadweight/.

Layout (mirrors beads):
    .deadweight/
      deadends.jsonl   — source of truth, committed to git
      deadends.db      — SQLite index, rebuildable, gitignored
      config.yaml      — repo id, sync branch

The JSONL is authoritative. The SQLite DB is a cache built from it. If the JSONL
is newer than the DB, we rebuild on next access. All writes append to the JSONL
first, then insert into the index.

Resolution deltas in the JSONL look like:
    {"id": "<id>", "_resolved": true, "_resolved_at": "<iso-ts>"}
These are applied on rebuild to set resolved=1 on the matching dead end.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
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
    created_at TEXT NOT NULL,
    resolved INTEGER DEFAULT 0,
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_repo ON dead_ends(repo);
CREATE INDEX IF NOT EXISTS idx_repo_path ON dead_ends(repo, path);
CREATE INDEX IF NOT EXISTS idx_approach ON dead_ends(approach);
CREATE INDEX IF NOT EXISTS idx_created_at ON dead_ends(created_at);
"""


# ---------------------------------------------------------------------------
# FTS5 availability check
# ---------------------------------------------------------------------------


def _check_fts5() -> bool:
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE _t USING fts5(x)")
        conn.close()
        return True
    except sqlite3.OperationalError:
        return False


_FTS5_AVAILABLE = _check_fts5()


def _build_fts_query(approach: str) -> str | None:
    """Convert a natural-language approach string to an FTS5 MATCH expression.

    Each word becomes a quoted token (exact-word match) joined with OR so that
    BM25 ranks entries containing more keywords higher.
    """
    words = re.sub(r"[^\w\s]", " ", approach).split()
    words = [w for w in words if len(w) >= 2]
    if not words:
        return None
    return " OR ".join(f'"{w}"' for w in words)


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


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Add columns introduced after the initial schema, and create the FTS table."""
    for stmt in [
        "ALTER TABLE dead_ends ADD COLUMN resolved INTEGER DEFAULT 0",
        "ALTER TABLE dead_ends ADD COLUMN resolved_at TEXT",
    ]:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()

    if not _FTS5_AVAILABLE:
        return

    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS dead_ends_fts USING fts5(
                id UNINDEXED,
                approach,
                reason,
                tokenize = 'unicode61'
            )
        """)
        conn.commit()
    except sqlite3.OperationalError as e:
        logger.warning("FTS5 table creation failed: %s", e)


def _ensure_fts_populated(conn: sqlite3.Connection) -> None:
    """Backfill the FTS index from dead_ends if it is empty but the table isn't."""
    if not _FTS5_AVAILABLE:
        return
    try:
        fts_count = conn.execute("SELECT COUNT(*) FROM dead_ends_fts").fetchone()[0]
        if fts_count > 0:
            return
        de_count = conn.execute(
            "SELECT COUNT(*) FROM dead_ends WHERE resolved = 0 OR resolved IS NULL"
        ).fetchone()[0]
        if de_count == 0:
            return
        conn.execute("""
            INSERT INTO dead_ends_fts(id, approach, reason)
            SELECT id, COALESCE(approach, ''), COALESCE(reason, '')
            FROM dead_ends WHERE resolved = 0 OR resolved IS NULL
        """)
        conn.commit()
    except sqlite3.OperationalError:
        pass


def _open(store: Path) -> sqlite3.Connection:
    """Open a connection, rebuilding the index if the jsonl is newer."""
    db = _db_path(store)
    rebuild = _needs_rebuild(store)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA_SQL)
    _apply_migrations(conn)
    if rebuild:
        _rebuild_from_jsonl(conn, _jsonl_path(store))
    else:
        _ensure_fts_populated(conn)
    return conn


def _rebuild_from_jsonl(conn: sqlite3.Connection, jsonl: Path) -> int:
    conn.execute("DELETE FROM dead_ends")
    if _FTS5_AVAILABLE:
        try:
            conn.execute("DELETE FROM dead_ends_fts")
        except sqlite3.OperationalError:
            pass

    count = 0
    resolutions: dict[str, str] = {}  # id -> resolved_at ISO string

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

            if data.get("_resolved"):
                resolutions[data["id"]] = data.get("_resolved_at", "")
            else:
                _insert_row(conn, data, update_fts=False)
                count += 1

    # Apply resolution deltas
    for id_, resolved_at in resolutions.items():
        conn.execute(
            "UPDATE dead_ends SET resolved = 1, resolved_at = ? WHERE id = ?",
            (resolved_at, id_),
        )

    conn.commit()

    # Bulk-populate FTS for unresolved entries only
    if _FTS5_AVAILABLE:
        try:
            conn.execute("""
                INSERT INTO dead_ends_fts(id, approach, reason)
                SELECT id, COALESCE(approach, ''), COALESCE(reason, '')
                FROM dead_ends WHERE resolved = 0 OR resolved IS NULL
            """)
            conn.commit()
        except sqlite3.OperationalError:
            pass

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


def _insert_row(conn: sqlite3.Connection, data: dict, update_fts: bool = True) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO dead_ends
           (id, repo, path, approach, reason, turns_wasted, agent, version, task_id, created_at, resolved, resolved_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            data.get("resolved", 0),
            data.get("resolved_at"),
        ),
    )
    if update_fts and _FTS5_AVAILABLE and not data.get("resolved"):
        try:
            conn.execute(
                "INSERT OR REPLACE INTO dead_ends_fts(id, approach, reason) VALUES (?, ?, ?)",
                (data.get("id"), data.get("approach") or "", data.get("reason") or ""),
            )
        except sqlite3.OperationalError:
            pass


def append_dead_end(store: Path, entry: DeadEndCreate) -> DeadEnd:
    """Append an entry to the jsonl and insert into the index."""
    dead_end = DeadEnd(**entry.model_dump())
    row = dead_end.model_dump()
    row["created_at"] = dead_end.created_at.isoformat()
    row["agent"] = dead_end.agent.value if dead_end.agent else None

    jsonl_row = {k: v for k, v in row.items() if v is not None}
    jsonl_row.pop("relevance_score", None)
    # Don't persist default False resolved state
    if not jsonl_row.get("resolved"):
        jsonl_row.pop("resolved", None)
        jsonl_row.pop("resolved_at", None)

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
    resolved_at_raw = row.get("resolved_at")
    resolved_at = (
        datetime.fromisoformat(resolved_at_raw)
        if isinstance(resolved_at_raw, str) and resolved_at_raw
        else None
    )
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
        resolved=bool(row.get("resolved", False)),
        resolved_at=resolved_at,
    )


def _query_fts(
    conn: sqlite3.Connection,
    approach: str,
    repo: str | None,
    path: str | None,
    agent: str | None,
    limit: int,
    include_resolved: bool,
) -> list[DeadEnd]:
    """Search dead ends using SQLite FTS5 with BM25 ranking."""
    fts_query = _build_fts_query(approach)
    if not fts_query:
        return []

    try:
        fts_rows = conn.execute(
            "SELECT id, rank FROM dead_ends_fts WHERE dead_ends_fts MATCH ? ORDER BY rank LIMIT ?",
            [fts_query, limit * 4],
        ).fetchall()
    except sqlite3.OperationalError:
        return []

    if not fts_rows:
        return []

    ids = [r[0] for r in fts_rows]
    rank_by_id = {r[0]: i for i, r in enumerate(fts_rows)}

    placeholders = ",".join("?" * len(ids))
    clauses = [f"id IN ({placeholders})"]
    params: list = ids[:]
    if repo:
        clauses.append("repo = ?")
        params.append(repo)
    if path:
        clauses.append("path LIKE ?")
        params.append(f"{path}%")
    if agent:
        clauses.append("agent = ?")
        params.append(agent)
    if not include_resolved:
        clauses.append("(resolved = 0 OR resolved IS NULL)")

    where = " WHERE " + " AND ".join(clauses)
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM dead_ends{where}", params).fetchall()]

    results = [_row_to_dead_end(r) for r in rows]
    results.sort(key=lambda de: rank_by_id.get(de.id, 999))
    results = results[:limit]

    n = len(results)
    for i, de in enumerate(results):
        de.relevance_score = round(1.0 - i / max(n, 1), 2)

    return results


def query_dead_ends(
    store: Path,
    repo: str | None = None,
    path: str | None = None,
    approach: str | None = None,
    agent: str | None = None,
    limit: int = 10,
    include_resolved: bool = False,
) -> list[DeadEnd]:
    conn = _open(store)
    try:
        # FTS only indexes unresolved entries; bypass it when resolved results are wanted
        if approach and _FTS5_AVAILABLE and not include_resolved:
            return _query_fts(conn, approach, repo, path, agent, limit, include_resolved)

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
        if not include_resolved:
            clauses.append("(resolved = 0 OR resolved IS NULL)")

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM dead_ends{where} ORDER BY created_at DESC"

        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()

    results = [_row_to_dead_end(r) for r in rows]

    if approach:
        # FTS5 unavailable fallback: keyword scoring over approach + reason
        keywords = approach.lower().split()
        scored = []
        for de in results:
            text = (de.approach + " " + (de.reason or "")).lower()
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


def update_dead_end(store: Path, id_: str) -> DeadEnd | None:
    """Mark a dead end as resolved.

    Appends a resolution delta to the JSONL (keeps it append-only) and updates
    the SQLite index immediately. The delta is replayed on the next `dw rebuild`.
    """
    de = get_dead_end(store, id_)
    if de is None:
        return None

    now = datetime.now(timezone.utc)
    delta = {"id": id_, "_resolved": True, "_resolved_at": now.isoformat()}
    with _jsonl_path(store).open("a", encoding="utf-8") as f:
        f.write(json.dumps(delta) + "\n")

    conn = _open(store)
    try:
        conn.execute(
            "UPDATE dead_ends SET resolved = 1, resolved_at = ? WHERE id = ?",
            (now.isoformat(), id_),
        )
        if _FTS5_AVAILABLE:
            try:
                conn.execute("DELETE FROM dead_ends_fts WHERE id = ?", (id_,))
            except sqlite3.OperationalError:
                pass
        conn.commit()
    finally:
        conn.close()

    de.resolved = True
    de.resolved_at = now
    return de


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
