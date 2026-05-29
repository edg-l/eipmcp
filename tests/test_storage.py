from datetime import UTC, datetime

from eipmcp import storage


def test_eip_roundtrip(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    monkeypatch.setenv("EIPMCP_DATA_DIR", str(tmp_path))
    with storage.connect(db) as conn:
        storage.upsert_eip(conn, {
            "repo": "eips", "number": 1, "title": "T", "status": "Final",
            "type": "Standards Track", "category": "Core", "author": "A",
            "created": "2015", "requires": [], "discussions": None,
            "file_path": "EIPS/eip-1.md", "body": "hi", "content_sha": "x" * 64,
        })
        storage.upsert_eip(conn, {
            "repo": "eips", "number": 2, "title": "U", "status": "Draft",
            "type": "Standards Track", "category": "Core", "author": "B",
            "created": "2016", "requires": [1], "discussions": None,
            "file_path": "EIPS/eip-2.md", "body": "deps on 1", "content_sha": "y" * 64,
        })
        assert storage.get_eip(conn, 1)["title"] == "T"
        assert [r["number"] for r in storage.list_eips(conn, status="Draft")] == [2]
        rb = storage.required_by(conn, 1)
        assert [r["number"] for r in rb] == [2]


def test_sync_log(tmp_path):
    db = tmp_path / "s.db"
    with storage.connect(db) as conn:
        storage.record_sync(conn, "eips", "aaa", datetime.now(UTC).isoformat())
        storage.record_sync(conn, "eips", "bbb", datetime.now(UTC).isoformat())
        last = storage.last_sync(conn, "eips")
        prev = storage.previous_sync(conn, "eips")
        assert last["commit_sha"] == "bbb"
        assert prev["commit_sha"] == "aaa"
