import pytest

from eipmcp import hardforks, storage


@pytest.fixture
def populated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("EIPMCP_DATA_DIR", str(tmp_path))
    with storage.connect() as conn:
        # Meta EIP for a fictional Pectra
        storage.upsert_eip(conn, {
            "repo": "eips", "number": 7600, "title": "Hardfork Meta: Prague-Pectra",
            "description": None, "status": "Final", "type": "Meta", "category": None,
            "author": "x", "created": "2024", "requires": [], "discussions": None,
            "file_path": "EIPS/eip-7600.md",
            "body": "Includes EIP-7702, EIP-7251 and EIP-2537.",
            "content_sha": "0" * 64,
        })
        for n in (7702, 7251, 2537):
            storage.upsert_eip(conn, {
                "repo": "eips", "number": n, "title": f"T{n}", "description": None,
                "status": "Final", "type": "Standards Track", "category": "Core",
                "author": "x", "created": "2024", "requires": [], "discussions": None,
                "file_path": f"EIPS/eip-{n}.md", "body": "x",
                "content_sha": f"{n:064d}",
            })
    return tmp_path


def test_lookup_pectra_finds_meta_and_included(populated_db):
    result = hardforks.lookup("pectra")
    assert any(m["number"] == 7600 for m in result["matches"])
    included = {e["number"] for e in result["included_eips"]}
    assert {7702, 7251, 2537} <= included
    # All included EIPs are indexed in this fixture
    assert all(e["indexed"] for e in result["included_eips"])


def test_lookup_alias_resolution(populated_db):
    # "prague" should resolve via aliases to the same meta
    result = hardforks.lookup("prague")
    assert "pectra" in result["resolved_aliases"]
    assert any(m["number"] == 7600 for m in result["matches"])


def test_lookup_unknown_returns_empty(populated_db):
    result = hardforks.lookup("doesnotexistfork")
    assert result["matches"] == []
    assert result["included_eips"] == []


def test_list_all_meta_only(populated_db):
    metas = hardforks.list_all()
    nums = {m["number"] for m in metas}
    assert 7600 in nums
    assert 7702 not in nums
