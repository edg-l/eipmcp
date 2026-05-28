from eipmcp.eips import parse_eip_file


SAMPLE = """---
eip: 1559
title: Fee market change for ETH 1.0 chain
author: Vitalik Buterin (@vbuterin)
discussions-to: https://ethereum-magicians.org/t/eip-1559
status: Final
type: Standards Track
category: Core
created: 2019-04-13
requires: 2718, 2930
---

## Abstract

A new transaction format.
"""


def test_parse_minimal_eip():
    row = parse_eip_file(SAMPLE, "EIPS/eip-1559.md", "eips")
    assert row is not None
    assert row["number"] == 1559
    assert row["status"] == "Final"
    assert row["category"] == "Core"
    assert row["requires"] == [2718, 2930]
    assert "Abstract" in row["body"]
    assert len(row["content_sha"]) == 64


def test_requires_handles_string_form():
    text = SAMPLE.replace("requires: 2718, 2930", 'requires: "2718, 2930"')
    row = parse_eip_file(text, "EIPS/eip-1559.md", "eips")
    assert row is not None
    assert row["requires"] == [2718, 2930]


def test_non_eip_filename_returns_none():
    row = parse_eip_file(SAMPLE, "EIPS/README.md", "eips")
    assert row is None
