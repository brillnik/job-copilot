from typing import Any, Generic, TypeVar

from sqlalchemy.orm import Session

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic data access. Repositories are the only layer that touches the Session."""

    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, id: Any) -> ModelT | None:
        return self.session.get(self.model, id)

    def add(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        self.session.commit()
        return obj

    def update(self, obj: ModelT) -> ModelT:
        self.session.commit()
        return obj

    def delete(self, obj: ModelT) -> None:
        self.session.delete(obj)
        self.session.commit()
