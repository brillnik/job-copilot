import re


def norm(text: str) -> str:
    """Case, whitespace and punctuation-insensitive form used by verbatim checks."""
    return re.sub(r"[\W_]+", "", text.casefold())
