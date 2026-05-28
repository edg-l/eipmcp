"""SQLite schema and helpers for EIP/spec indexing."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .config import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS eips (
    repo         TEXT NOT NULL,
    number       INTEGER NOT NULL,
    title        TEXT,
    description  TEXT,
    status       TEXT,
    type         TEXT,
    category     TEXT,
    author       TEXT,
    created      TEXT,
    requires     TEXT,           -- JSON array of EIP numbers
    discussions  TEXT,
    file_path    TEXT NOT NULL,  -- relative to repo root
    body         TEXT NOT NULL,
    content_sha  TEXT NOT NULL,
    PRIMARY KEY (repo, number)
);

CREATE INDEX IF NOT EXISTS idx_eips_status  ON eips(status);
CREATE INDEX IF NOT EXISTS idx_eips_type    ON eips(type);
CREATE INDEX IF NOT EXISTS idx_eips_cat     ON eips(category);

CREATE VIRTUAL TABLE IF NOT EXISTS eips_fts USING fts5(
    repo, number UNINDEXED, title, description, body,
    tokenize = 'porter unicode61'
);

CREATE TABLE IF NOT EXISTS specs (
    repo         TEXT NOT NULL,
    path         TEXT NOT NULL,
    body         TEXT NOT NULL,
    content_sha  TEXT NOT NULL,
    PRIMARY KEY (repo, path)
);

CREATE TABLE IF NOT EXISTS eip_refs (
    eip_number   INTEGER NOT NULL,
    source_repo  TEXT NOT NULL,
    source_path  TEXT NOT NULL,
    PRIMARY KEY (eip_number, source_repo, source_path)
);
CREATE INDEX IF NOT EXISTS idx_refs_eip ON eip_refs(eip_number);
CREATE INDEX IF NOT EXISTS idx_refs_src ON eip_refs(source_repo, source_path);

CREATE TABLE IF NOT EXISTS sync_log (
    repo       TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    synced_at  TEXT NOT NULL,    -- ISO-8601
    PRIMARY KEY (repo, commit_sha)
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply schema migrations for DBs created by older versions."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(eips)").fetchall()}
    if "description" not in cols:
        conn.execute("ALTER TABLE eips ADD COLUMN description TEXT")


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    p = path or db_path()
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------- EIPs ----------

def upsert_eip(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    requires = row.get("requires") or []
    if not isinstance(requires, str):
        requires = json.dumps(requires)
    payload = {**row, "requires": requires, "description": row.get("description")}
    conn.execute(
        """
        INSERT INTO eips (repo, number, title, description, status, type, category, author,
                          created, requires, discussions, file_path, body, content_sha)
        VALUES (:repo, :number, :title, :description, :status, :type, :category, :author,
                :created, :requires, :discussions, :file_path, :body, :content_sha)
        ON CONFLICT(repo, number) DO UPDATE SET
            title=excluded.title, description=excluded.description, status=excluded.status,
            type=excluded.type, category=excluded.category, author=excluded.author,
            created=excluded.created, requires=excluded.requires, discussions=excluded.discussions,
            file_path=excluded.file_path, body=excluded.body, content_sha=excluded.content_sha
        """,
        payload,
    )
    # Keep FTS in sync.
    conn.execute(
        "DELETE FROM eips_fts WHERE repo=? AND number=?", (row["repo"], row["number"])
    )
    conn.execute(
        "INSERT INTO eips_fts (repo, number, title, description, body) VALUES (?, ?, ?, ?, ?)",
        (row["repo"], row["number"], row.get("title"), row.get("description"), row["body"]),
    )


def get_eip(conn: sqlite3.Connection, number: int, repo: str = "eips") -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM eips WHERE repo=? AND number=?", (repo, number))
    row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    d["requires"] = json.loads(d["requires"]) if d.get("requires") else []
    return d


def list_eips(
    conn: sqlite3.Connection,
    repo: str | None = None,
    status: str | None = None,
    type_: str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    sql = (
        "SELECT repo, number, title, description, status, type, category "
        "FROM eips WHERE 1=1"
    )
    args: list[Any] = []
    if repo:
        sql += " AND repo=?"; args.append(repo)
    if status:
        sql += " AND status=?"; args.append(status)
    if type_:
        sql += " AND type=?"; args.append(type_)
    if category:
        sql += " AND category=?"; args.append(category)
    sql += " ORDER BY number"
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def _fts_query(raw: str) -> str:
    """Quote each token so FTS5 operators in user input don't blow up."""
    tokens = [t for t in raw.split() if t]
    if not tokens:
        return '""'
    return " ".join(f'"{t.replace(chr(34), "")}"' for t in tokens)


def search_eips(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 50,
    snippet_words: int = 12,
) -> list[dict[str, Any]]:
    """FTS5 search over title/description/body, ranked by bm25."""
    fts_q = _fts_query(query)
    try:
        rows = conn.execute(
            """
            SELECT repo, number, title, description,
                   snippet(eips_fts, 4, '«', '»', '…', ?) AS snippet,
                   bm25(eips_fts) AS rank
            FROM eips_fts
            WHERE eips_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (snippet_words, fts_q, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        # Fallback to LIKE if FTS parsing somehow still fails.
        pat = f"%{query}%"
        rows = conn.execute(
            """
            SELECT repo, number, title, description, NULL AS snippet, 0 AS rank
            FROM eips
            WHERE title LIKE ? OR description LIKE ? OR body LIKE ?
            ORDER BY number
            LIMIT ?
            """,
            (pat, pat, pat, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def required_by(conn: sqlite3.Connection, number: int, repo: str = "eips") -> list[dict[str, Any]]:
    needle = str(number)
    rows = conn.execute(
        "SELECT number, title, status, requires FROM eips WHERE repo=? AND requires LIKE ?",
        (repo, f"%{needle}%"),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        reqs = json.loads(r["requires"]) if r["requires"] else []
        if number in [int(x) for x in reqs if str(x).isdigit()]:
            out.append({"number": r["number"], "title": r["title"], "status": r["status"]})
    return out


# ---------- Specs ----------

def upsert_spec(conn: sqlite3.Connection, repo: str, path: str, body: str, sha: str) -> None:
    conn.execute(
        """
        INSERT INTO specs (repo, path, body, content_sha) VALUES (?, ?, ?, ?)
        ON CONFLICT(repo, path) DO UPDATE SET body=excluded.body, content_sha=excluded.content_sha
        """,
        (repo, path, body, sha),
    )


def get_spec(conn: sqlite3.Connection, repo: str, path: str) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM specs WHERE repo=? AND path=?", (repo, path))
    row = cur.fetchone()
    return dict(row) if row else None


def list_specs(
    conn: sqlite3.Connection, repo: str, glob: str | None = None
) -> list[dict[str, Any]]:
    sql = "SELECT repo, path FROM specs WHERE repo=?"
    args: list[Any] = [repo]
    if glob:
        sql += " AND path LIKE ?"
        args.append(glob.replace("*", "%"))
    sql += " ORDER BY path"
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


# ---------- Cross-references ----------

def replace_refs(
    conn: sqlite3.Connection,
    source_repo: str,
    source_path: str,
    eip_numbers: Iterable[int],
) -> None:
    conn.execute(
        "DELETE FROM eip_refs WHERE source_repo=? AND source_path=?",
        (source_repo, source_path),
    )
    nums = list(eip_numbers)
    if nums:
        conn.executemany(
            "INSERT OR IGNORE INTO eip_refs (eip_number, source_repo, source_path) "
            "VALUES (?, ?, ?)",
            [(n, source_repo, source_path) for n in nums],
        )


def refs_for_eip(
    conn: sqlite3.Connection, number: int, repo: str | None = None
) -> list[dict[str, Any]]:
    sql = "SELECT source_repo, source_path FROM eip_refs WHERE eip_number=?"
    args: list[Any] = [number]
    if repo:
        sql += " AND source_repo=?"; args.append(repo)
    sql += " ORDER BY source_repo, source_path"
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def refs_in_source(conn: sqlite3.Connection, repo: str, path: str) -> list[int]:
    rows = conn.execute(
        "SELECT eip_number FROM eip_refs WHERE source_repo=? AND source_path=? "
        "ORDER BY eip_number",
        (repo, path),
    ).fetchall()
    return [r["eip_number"] for r in rows]


# ---------- Cleanup ----------

def delete_missing_eips(conn: sqlite3.Connection, repo: str, present: Iterable[int]) -> int:
    present_set = set(present)
    existing_rows = conn.execute(
        "SELECT number, file_path FROM eips WHERE repo=?", (repo,)
    ).fetchall()
    to_delete = [(r["number"], r["file_path"]) for r in existing_rows
                 if r["number"] not in present_set]
    if to_delete:
        conn.executemany(
            "DELETE FROM eips WHERE repo=? AND number=?",
            [(repo, n) for n, _ in to_delete],
        )
        conn.executemany(
            "DELETE FROM eips_fts WHERE repo=? AND number=?",
            [(repo, n) for n, _ in to_delete],
        )
        conn.executemany(
            "DELETE FROM eip_refs WHERE source_repo=? AND source_path=?",
            [(repo, p) for _, p in to_delete],
        )
    return len(to_delete)


def delete_missing_specs(conn: sqlite3.Connection, repo: str, present: Iterable[str]) -> int:
    present_set = set(present)
    existing = {r["path"] for r in conn.execute(
        "SELECT path FROM specs WHERE repo=?", (repo,)
    ).fetchall()}
    to_delete = existing - present_set
    if to_delete:
        conn.executemany(
            "DELETE FROM specs WHERE repo=? AND path=?",
            [(repo, p) for p in to_delete],
        )
        conn.executemany(
            "DELETE FROM eip_refs WHERE source_repo=? AND source_path=?",
            [(repo, p) for p in to_delete],
        )
    return len(to_delete)


# ---------- Sync log ----------

def record_sync(conn: sqlite3.Connection, repo: str, commit: str, when_iso: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO sync_log (repo, commit_sha, synced_at) VALUES (?, ?, ?)",
        (repo, commit, when_iso),
    )


def last_sync(conn: sqlite3.Connection, repo: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT commit_sha, synced_at FROM sync_log WHERE repo=? ORDER BY synced_at DESC LIMIT 1",
        (repo,),
    ).fetchone()
    return dict(row) if row else None


def previous_sync(
    conn: sqlite3.Connection, repo: str, before_commit: str | None = None
) -> dict[str, Any] | None:
    if before_commit is None:
        latest = last_sync(conn, repo)
        if not latest:
            return None
        before_commit = latest["commit_sha"]
    row = conn.execute(
        """
        SELECT commit_sha, synced_at FROM sync_log
        WHERE repo=? AND commit_sha != ?
        ORDER BY synced_at DESC LIMIT 1
        """,
        (repo, before_commit),
    ).fetchone()
    return dict(row) if row else None
