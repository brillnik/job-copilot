import logging
import uuid
from pathlib import PurePath
from typing import BinaryIO

from app.core.exceptions import EmptyFile, FileTooLarge, UnsupportedFileType
from app.models.resume import Resume
from app.repositories.manager import RepositoryManager
from app.storage.base import Storage

log = logging.getLogger(__name__)

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
        return self.ingest(user_id, filename, stream)[0]

    def ingest(
        self, user_id: uuid.UUID, filename: str, stream: BinaryIO
    ) -> tuple[Resume, bytes]:
        """Validate and store an upload, returning the row and the validated bytes."""
        # The filename is user data; only its extension is logged.
        ext = PurePath(filename).suffix.lower()
        if ext not in FORMATS:
            log.warning("resume rejected user=%s reason=extension ext=%r", user_id, ext)
            raise UnsupportedFileType("Only PDF and DOCX are supported")

        data = stream.read(self.max_bytes + 1)
        if len(data) > self.max_bytes:
            log.warning(
                "resume rejected user=%s reason=too_large limit=%d",
                user_id,
                self.max_bytes,
            )
            raise FileTooLarge(f"File exceeds {self.max_bytes} bytes")
        if not data:
            log.warning("resume rejected user=%s reason=empty", user_id)
            raise EmptyFile()
        if not data.startswith(FORMATS[ext]):
            log.warning(
                "resume rejected user=%s reason=content_mismatch ext=%s", user_id, ext
            )
            raise UnsupportedFileType("File content does not match its extension")

        resume_id = uuid.uuid4().hex
        key = f"{user_id.hex}/{resume_id}{ext}"
        self.storage.save(key, data)
        log.debug("resume stored key=%s size=%d", key, len(data))
        try:
            resume = self.repos.resumes.add(
                Resume(
                    id=resume_id,
                    user_id=user_id,
                    filename=filename,
                    size=len(data),
                    storage_key=key,
                )
            )
            log.info(
                "resume uploaded user=%s id=%s ext=%s size=%d",
                user_id,
                resume_id,
                ext,
                len(data),
            )
            return resume, data
        except Exception as e:
            log.error(
                "resume db insert failed id=%s error=%s; removing stored file",
                resume_id,
                type(e).__name__,
            )
            self.storage.delete(key)
            raise
