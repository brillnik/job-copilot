import uuid

from sqlalchemy import select

from app.models.screening import ScreeningAnswer
from app.repositories.base import BaseRepository


class ScreeningRepository(BaseRepository[ScreeningAnswer]):
    """Every query takes user_id; another user's id looks like a missing row."""

    model = ScreeningAnswer

    def get_for_user(
        self, user_id: uuid.UUID, answer_id: str
    ) -> ScreeningAnswer | None:
        return self.session.scalar(
            select(ScreeningAnswer).where(
                ScreeningAnswer.id == answer_id, ScreeningAnswer.user_id == user_id
            )
        )

    def list_for_user(
        self, user_id: uuid.UUID, field_type: str | None = None
    ) -> list[ScreeningAnswer]:
        stmt = select(ScreeningAnswer).where(ScreeningAnswer.user_id == user_id)
        if field_type:
            stmt = stmt.where(ScreeningAnswer.field_type == field_type)
        return list(
            self.session.scalars(
                stmt.order_by(ScreeningAnswer.updated_at.desc(), ScreeningAnswer.id)
            )
        )

    def by_normalised(
        self, user_id: uuid.UUID, normalised: str, field_type: str
    ) -> ScreeningAnswer | None:
        return self.session.scalar(
            select(ScreeningAnswer).where(
                ScreeningAnswer.user_id == user_id,
                ScreeningAnswer.normalised_question == normalised,
                ScreeningAnswer.field_type == field_type,
            )
        )
