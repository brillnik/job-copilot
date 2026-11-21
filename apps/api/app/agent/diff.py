"""Word-level diff between a source bullet and its tailored text."""

import re
from difflib import SequenceMatcher

from app.schemas.run import DiffSegment

_TOKEN = re.compile(r"\s+|[^\s]+")


def word_diff(old: str, new: str) -> list[DiffSegment]:
    """Segments whose `same`+`del` text rebuild `old` and `same`+`add` rebuild `new`."""
    a, b = _TOKEN.findall(old), _TOKEN.findall(new)
    segs: list[DiffSegment] = []

    def push(op: str, tokens: list[str]) -> None:
        text = "".join(tokens)
        if not text:
            return
        if segs and segs[-1].op == op:
            segs[-1].text += text
        else:
            segs.append(DiffSegment(op=op, text=text))  # type: ignore[arg-type]

    for tag, i1, i2, j1, j2 in SequenceMatcher(
        None, a, b, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            push("same", a[i1:i2])
        else:
            push("del", a[i1:i2])
            push("add", b[j1:j2])
    return segs
