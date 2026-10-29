import uuid
from pathlib import PurePath
from typing import BinaryIO

from app.core.exceptions import EmptyFile, FileTooLarge, UnsupportedFileType
from app.models.resume import Resume
from app.repositories.manager import RepositoryManager
from app.storage.base import Storage

# extension -> magic bytes. Content is sniffed, the client's content-type is not trusted.
FORMATS = {
    ".pdf": b"%PDF-",
    ".docx": b"PK\x03\x04",
}


class ResumeService:
    def __init__(
        self, repos: RepositoryManager, storage: Storage, max_bytes: int
    ) -> None:
        self.repos = repos
        self.storage = storage
        self.max_bytes = max_bytes

    def upload(self, user_id: uuid.UUID, filename: str, stream: BinaryIO) -> Resume:
        ext = PurePath(filename).suffix.lower()
        if ext not in FORMATS:
            raise UnsupportedFileType("Only PDF and DOCX are supported")

        data = stream.read(self.max_bytes + 1)
        if len(data) > self.max_bytes:
            raise FileTooLarge(f"File exceeds {self.max_bytes} bytes")
        if not data:
            raise EmptyFile()
        if not data.startswith(FORMATS[ext]):
            raise UnsupportedFileType("File content does not match its extension")

        resume_id = uuid.uuid4().hex
        key = f"{user_id.hex}/{resume_id}{ext}"
        self.storage.save(key, data)
        try:
            return self.repos.resumes.add(
                Resume(
                    id=resume_id,
                    user_id=user_id,
                    filename=filename,
                    size=len(data),
                    storage_key=key,
                )
            )
        except Exception:
            self.storage.delete(key)
            raise
