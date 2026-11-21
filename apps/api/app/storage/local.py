import shutil
from pathlib import Path


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("Storage key escapes the storage root")
        return path

    def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def list_prefix(self, prefix: str) -> list[str]:
        stripped = prefix.strip("/")
        base = self._path(stripped) if stripped else self.root
        if not base.exists():
            return []
        if base.is_file():
            return [base.relative_to(self.root).as_posix()]
        return sorted(
            p.relative_to(self.root).as_posix() for p in base.rglob("*") if p.is_file()
        )

    def delete_prefix(self, prefix: str) -> int:
        keys = self.list_prefix(prefix)
        for key in keys:
            self._path(key).unlink(missing_ok=True)
        base = self._path(prefix.strip("/"))
        if base.is_dir():
            shutil.rmtree(base, ignore_errors=True)
        return len(keys)
