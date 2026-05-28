from eipmcp.recent import _eip_number_from_path, recent_changes


def test_eip_number_extraction():
    assert _eip_number_from_path("EIPS/eip-1559.md") == 1559
    assert _eip_number_from_path("ERCS/erc-20.md") == 20
    assert _eip_number_from_path("EIPS/eip-7702.MD") == 7702
    assert _eip_number_from_path("EIPS/README.md") is None
    assert _eip_number_from_path("specs/electra/beacon-chain.md") is None


def test_recent_changes_returns_no_baseline_note_when_empty(tmp_path, monkeypatch):
    """With no sync_log rows, recent_changes reports the missing baseline."""
    monkeypatch.setenv("EIPMCP_DATA_DIR", str(tmp_path))
    out = recent_changes(days=7, repo="eips")
    assert len(out) == 1
    assert "no sync" in (out[0].get("note") or "")
    assert out[0]["total"] == 0
