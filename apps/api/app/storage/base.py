from typing import Protocol


class Storage(Protocol):
    """File blob storage. Swap the implementation (e.g. S3) without touching services."""

    def save(self, key: str, data: bytes) -> None: ...

    def delete(self, key: str) -> None: ...
