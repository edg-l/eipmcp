"""Extract `EIP-NNNN` style references from arbitrary text and paths."""

import re

# `(?!\d)` instead of `\b` at the tail: `\b` doesn't fire between a digit and
# an underscore (both are word chars), which would miss `eip7702_set_code_tx`.
# `(?!\d)` also keeps the oversize-number guard intact — `\d{1,5}` followed by
# another digit fails the lookahead at every greedy length, so `EIP1234567`
# matches nothing.
_BODY_RE = re.compile(r"\bEIPS?[\s\-]?(\d{1,5})(?!\d)", re.IGNORECASE)
_PATH_RE = re.compile(r"\beip[-_]?(\d{1,5})(?!\d)", re.IGNORECASE)


def extract_refs(text: str, path: str = "", exclude: int | None = None) -> set[int]:
    """Pull out EIP numbers mentioned in body text and (optionally) in the file path.

    `exclude` suppresses self-references (when scanning EIP-N's own file).
    """
    refs: set[int] = set()
    for m in _BODY_RE.findall(text):
        n = int(m)
        if 1 <= n <= 99999:
            refs.add(n)
    if path:
        for m in _PATH_RE.findall(path):
            n = int(m)
            if 1 <= n <= 99999:
                refs.add(n)
    if exclude is not None:
        refs.discard(exclude)
    return refs
