from datetime import datetime, timedelta, timezone

from eipmcp import storage, sync


def test_parse_ttl_units():
    assert sync.parse_ttl("0") == 0
    assert sync.parse_ttl("") == 0
    assert sync.parse_ttl("60s") == 60
    assert sync.parse_ttl("5m") == 300
    assert sync.parse_ttl("24h") == 86400
    assert sync.parse_ttl("1d") == 86400
    assert sync.parse_ttl("3600") == 3600
    assert sync.parse_ttl("garbage") == 0


def test_stale_repos_empty_db_skips_uninitialized(tmp_path, monkeypatch):
    monkeypatch.setenv("EIPMCP_DATA_DIR", str(tmp_path))
    # Default: never-synced repos are NOT counted (keeps startup fast).
    assert sync.stale_repos(60) == []


def test_stale_repos_include_uninitialized_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("EIPMCP_DATA_DIR", str(tmp_path))
    from eipmcp.config import REPOS
    stale = sync.stale_repos(60, include_uninitialized=True)
    assert set(stale) == set(REPOS)


def test_stale_repos_respects_fresh_sync(tmp_path, monkeypatch):
    monkeypatch.setenv("EIPMCP_DATA_DIR", str(tmp_path))
    now = datetime.now(timezone.utc)
    with storage.connect() as conn:
        storage.record_sync(conn, "eips", "abc", now.isoformat())
    stale = sync.stale_repos(60)
    assert "eips" not in stale


def test_stale_repos_zero_ttl_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("EIPMCP_DATA_DIR", str(tmp_path))
    assert sync.stale_repos(0) == []


def test_stale_repos_old_sync_is_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("EIPMCP_DATA_DIR", str(tmp_path))
    long_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    with storage.connect() as conn:
        storage.record_sync(conn, "eips", "old", long_ago)
    stale = sync.stale_repos(60)
    assert "eips" in stale
