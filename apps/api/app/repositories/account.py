import uuid

from sqlalchemy import select

from app.models.account import ConsentLog, Export
from app.models.job import AgentRun
from app.repositories.base import BaseRepository


class AccountRepository(BaseRepository[Export]):
    """Consent log, exports and the user's runs; every query takes user_id."""

    model = Export

    def latest_consent(self, user_id: uuid.UUID) -> ConsentLog | None:
        return self.session.scalar(
            select(ConsentLog)
            .where(ConsentLog.user_id == user_id)
            .order_by(ConsentLog.created_at.desc(), ConsentLog.id.desc())
            .limit(1)
        )

    def stage_consent(self, row: ConsentLog) -> ConsentLog:
        self.session.add(row)
        return row

    def pending_export(self, user_id: uuid.UUID) -> Export | None:
        return self.session.scalar(
            select(Export)
            .where(Export.user_id == user_id, Export.status.in_(("queued", "running")))
            .limit(1)
        )

    def stage_export(self, export: Export) -> Export:
        self.session.add(export)
        return export

    def get_export(self, user_id: uuid.UUID, export_id: str) -> Export | None:
        return self.session.scalar(
            select(Export).where(Export.id == export_id, Export.user_id == user_id)
        )

    def runs_in(self, user_id: uuid.UUID, statuses: tuple[str, ...]) -> list[AgentRun]:
        return list(
            self.session.scalars(
                select(AgentRun).where(
                    AgentRun.user_id == user_id, AgentRun.status.in_(statuses)
                )
            )
        )
