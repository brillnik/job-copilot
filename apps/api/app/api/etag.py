from app.services.job import Invalid


def etag(rev: int) -> str:
    return f'"{rev}"'


def parse_if_match(value: str | None) -> int | None:
    """The revision from an If-Match header, or None when the header is absent."""
    if value is None:
        return None
    raw = value.strip().removeprefix("W/").strip('"')
    try:
        return int(raw)
    except ValueError:
        raise Invalid("If-Match must be the ETag of the resource") from None
