from eipmcp import sync as sync_mod
from eipmcp.config import REPOS


def test_sync_all_continues_after_failure(monkeypatch):
    """One repo failing must not abort the others."""
    calls: list[str] = []

    def fake(key: str) -> dict:
        calls.append(key)
        if key == "ercs":
            raise RuntimeError("simulated network blip")
        return {"repo": key, "ok": True}

    monkeypatch.setattr(sync_mod, "sync_repo", fake)
    results = sync_mod.sync_all()

    assert calls == list(REPOS)
    by_repo = {r["repo"]: r for r in results}
    assert by_repo["ercs"]["error"] == "simulated network blip"
    assert by_repo["ercs"]["type"] == "RuntimeError"
    for k in REPOS:
        if k != "ercs":
            assert by_repo[k]["ok"] is True
