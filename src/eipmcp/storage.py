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

CREATE TABLE IF NOT EXISTS specs (
    repo         TEXT NOT NULL,
    path         TEXT NOT NULL,
    body         TEXT NOT NULL,
    content_sha  TEXT NOT NULL,
    PRIMARY KEY (repo, path)
);

CREATE TABLE IF NOT EXISTS sync_log (
    repo       TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    synced_at  TEXT NOT NULL,    -- ISO-8601
    PRIMARY KEY (repo, commit_sha)
);
"""


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    p = path or db_path()
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------- EIPs ----------

def upsert_eip(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    requires = row.get("requires") or []
    if not isinstance(requires, str):
        requires = json.dumps(requires)
    conn.execute(
        """
        INSERT INTO eips (repo, number, title, status, type, category, author,
                          created, requires, discussions, file_path, body, content_sha)
        VALUES (:repo, :number, :title, :status, :type, :category, :author,
                :created, :requires, :discussions, :file_path, :body, :content_sha)
        ON CONFLICT(repo, number) DO UPDATE SET
            title=excluded.title, status=excluded.status, type=excluded.type,
            category=excluded.category, author=excluded.author, created=excluded.created,
            requires=excluded.requires, discussions=excluded.discussions,
            file_path=excluded.file_path, body=excluded.body, content_sha=excluded.content_sha
        """,
        {**row, "requires": requires},
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
    sql = "SELECT repo, number, title, status, type, category FROM eips WHERE 1=1"
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


def search_eips(conn: sqlite3.Connection, query: str, limit: int = 50) -> list[dict[str, Any]]:
    pat = f"%{query}%"
    rows = conn.execute(
        """
        SELECT repo, number, title, status, type, category
        FROM eips
        WHERE title LIKE ? OR body LIKE ?
        ORDER BY number
        LIMIT ?
        """,
        (pat, pat, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def required_by(conn: sqlite3.Connection, number: int, repo: str = "eips") -> list[dict[str, Any]]:
    """EIPs whose `requires` includes `number`."""
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


def delete_missing_eips(conn: sqlite3.Connection, repo: str, present: Iterable[int]) -> int:
    present_set = set(present)
    existing = {r["number"] for r in conn.execute(
        "SELECT number FROM eips WHERE repo=?", (repo,)
    ).fetchall()}
    to_delete = existing - present_set
    if to_delete:
        conn.executemany(
            "DELETE FROM eips WHERE repo=? AND number=?",
            [(repo, n) for n in to_delete],
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
    """The sync immediately before `before_commit` (or before the latest if None)."""
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
