from eipmcp.crossrefs import extract_refs


def test_extract_body_forms():
    text = "See EIP-1559 and EIP 4844 and EIP2718 plus EIPS 7702 inside."
    assert extract_refs(text) == {1559, 4844, 2718, 7702}


def test_path_eip_dir_token():
    refs = extract_refs(
        "no body refs",
        path="tests/prague/eip7702_set_code_tx/test_set_code_txs.py",
    )
    assert 7702 in refs


def test_exclude_self():
    text = "EIP-1559 is this EIP."
    assert extract_refs(text, exclude=1559) == set()


def test_no_refs():
    assert extract_refs("nothing here") == set()


def test_ignores_oversize_numbers():
    # 7-digit number must not be picked up.
    assert extract_refs("EIP-1234567") == set()
