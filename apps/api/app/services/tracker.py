import logging
import uuid
from datetime import UTC, datetime, timedelta

from app.core.clock import week_start
from app.core.exceptions import Conflict, NotFound
from app.models.tracker import COLUMNS, TrackerCard
from app.repositories.manager import RepositoryManager
from app.schemas.tracker import (
    Board,
    Card,
    CardDetail,
    Stats,
    TrackerAdd,
    TrackerPatch,
)

log = logging.getLogger(__name__)

GAP = 1024.0  # spacing for fresh positions
MIN_GAP = 1e-6  # below this between neighbours, renumber the column


def _preview(notes: str | None) -> str | None:
    if not notes:
        return None
    flat = " ".join(notes.split())
    return flat if len(flat) <= 120 else flat[:119] + "…"


def _card(c: TrackerCard, company, title, score) -> Card:
    return Card(
        id=c.id,
        job_id=c.job_id,
        company=company,
        title=title,
        score=score,
        column=c.column,
        applied_at=c.applied_at,
        notes_preview=_preview(c.notes),
        updated_at=c.updated_at,
        rev=c.rev,
    )


class TrackerService:
    def __init__(self, repos: RepositoryManager) -> None:
        self.repos = repos

    def _own(self, user_id: uuid.UUID, card_id: str) -> TrackerCard:
        card = self.repos.tracker.get_for_user(user_id, card_id)
        if card is None:
            log.info("card not found user=%s card=%s", user_id, card_id)
            raise NotFound("Card not found")
        return card

    def _detail(self, user_id: uuid.UUID, card: TrackerCard) -> CardDetail:
        job = self.repos.jobs.get_for_user(user_id, card.job_id)
        base = _card(card, job and job.company, job and job.title, job and job.score)
        return CardDetail(
            **base.model_dump(),
            notes=card.notes,
            position=card.position,
            history=card.history or [],
        )

    # --- read ----------------------------------------------------------------
    def board(self, user_id: uuid.UUID) -> Board:
        cols: dict[str, list[Card]] = {c: [] for c in COLUMNS}
        for card, company, title, score in self.repos.tracker.board(user_id):
            cols[card.column].append(_card(card, company, title, score))
        now = datetime.now(UTC)
        agg = self.repos.tracker.stats(
            user_id, week_start=week_start(now), window_start=now - timedelta(days=30)
        )
        counts = self.repos.tracker.counts(user_id)
        applied = agg["applied_30d"]
        return Board(
            columns=cols,  # type: ignore[arg-type]
            stats=Stats(
                applied_this_week=agg["applied_this_week"],
                response_rate=round(agg["responses_30d"] / applied, 3)
                if applied
                else None,
                avg_match_score=agg["avg_match_score"],
                counts={c: counts.get(c, 0) for c in COLUMNS},  # type: ignore[misc]
            ),
        )

    def get(self, user_id: uuid.UUID, card_id: str) -> CardDetail:
        return self._detail(user_id, self._own(user_id, card_id))

    # --- write ---------------------------------------------------------------
    def add(self, user_id: uuid.UUID, body: TrackerAdd) -> CardDetail:
        if self.repos.jobs.get_for_user(user_id, body.job_id) is None:
            raise NotFound("Job not found")
        existing = self.repos.tracker.by_job(user_id, body.job_id)
        if existing is not None:
            raise Conflict(
                "This job is already on the board",
                code="already_tracked",
                details={"card_id": existing.id},
            )
        card = self._new_card(user_id, body.job_id, body.column)
        self.repos.session.commit()
        log.info("card added user=%s card=%s column=%s", user_id, card.id, card.column)
        return self._detail(user_id, card)

    def _new_card(self, user_id: uuid.UUID, job_id: str, column: str) -> TrackerCard:
        now = datetime.now(UTC)
        last = self.repos.tracker.last_position(user_id, column)
        card = TrackerCard(
            id=uuid.uuid4().hex,
            user_id=user_id,
            job_id=job_id,
            column=column,
            position=(last if last is not None else 0.0) + GAP,
            applied_at=now if column == "applied" else None,
            history=[{"from": None, "to": column, "at": now.isoformat()}],
            rev=1,
        )
        return self.repos.tracker.stage_add(card)

    def upsert_for_approval(self, user_id: uuid.UUID, job_id: str) -> TrackerCard:
        """Called inside the approve transaction (stages only, never commits).

        A second approval for the same job reuses the card. A card that is already
        further along (applied, interview, ...) keeps its column.
        """
        card = self.repos.tracker.by_job(user_id, job_id)
        if card is None:
            return self._new_card(user_id, job_id, "approved")
        card.updated_at = datetime.now(UTC)
        card.rev += 1
        return card

    def mark_applied(
        self, user_id: uuid.UUID, job_id: str, at: datetime
    ) -> TrackerCard:
        """Stages only. The card moves approved -> applied with applied_at; a card
        already further along keeps its column."""
        card = self.repos.tracker.by_job(user_id, job_id)
        if card is None:
            card = self._new_card(user_id, job_id, "applied")
            card.applied_at = at
            return card
        if card.column == "approved":
            card.history = [
                *(card.history or []),
                {"from": "approved", "to": "applied", "at": at.isoformat()},
            ]
            self._place(user_id, card, "applied", None)
            card.column = "applied"
        if card.applied_at is None:
            card.applied_at = at
        card.updated_at = at
        card.rev += 1
        return card

    def patch(
        self,
        user_id: uuid.UUID,
        card_id: str,
        body: TrackerPatch,
        if_match: int | None,
    ) -> CardDetail:
        card = self._own(user_id, card_id)
        expected = card.rev if if_match is None else if_match
        if not self.repos.tracker.cas_rev(user_id, card, expected):
            self.repos.session.rollback()
            self.repos.session.refresh(card)
            log.info("card stale write user=%s card=%s", user_id, card.id)
            raise Conflict(
                "The card changed since you loaded it",
                code="stale_write",
                details={"rev": card.rev},
            )
        fields = body.model_fields_set
        now = datetime.now(UTC)
        before = card.column
        target: str = body.column if body.column is not None else card.column
        if "notes" in fields:
            card.notes = body.notes
        if "applied_at" in fields:
            card.applied_at = body.applied_at
        if target != before:
            card.history = [
                *(card.history or []),
                {"from": before, "to": target, "at": now.isoformat()},
            ]
        if (
            target == "applied"
            and "applied_at" not in fields
            and card.applied_at is None
        ):
            card.applied_at = now
        if target != before or "position" in fields:
            self._place(user_id, card, target, body.position)
            card.column = target
        self.repos.session.commit()
        log.info(
            "card patched user=%s card=%s fields=%s column=%s->%s",
            user_id,
            card.id,
            sorted(fields),
            before,
            target,
        )
        return self._detail(user_id, card)

    def _place(
        self, user_id: uuid.UUID, card: TrackerCard, column: str, index: int | None
    ) -> None:
        """Put the card at `index` of `column` (default: the end) using a float midpoint."""
        others = self.repos.tracker.column_cards(user_id, column, exclude=card.id)
        i = len(others) if index is None else min(index, len(others))
        prev = others[i - 1].position if i > 0 else None
        nxt = others[i].position if i < len(others) else None
        if prev is None and nxt is None:
            card.position = GAP
        elif prev is None and nxt is not None:
            card.position = nxt - GAP
        elif nxt is None and prev is not None:
            card.position = prev + GAP
        elif prev is not None and nxt is not None and nxt - prev < MIN_GAP:
            self._rebalance(others, card, i)
        elif prev is not None and nxt is not None:
            card.position = (prev + nxt) / 2

    @staticmethod
    def _rebalance(others: list[TrackerCard], card: TrackerCard, index: int) -> None:
        ordered = [*others[:index], card, *others[index:]]
        for n, c in enumerate(ordered, 1):
            c.position = n * GAP
        log.info("tracker column rebalanced cards=%d", len(ordered))

    def delete(self, user_id: uuid.UUID, card_id: str) -> None:
        card = self._own(user_id, card_id)
        self.repos.tracker.stage_delete(card)
        self.repos.session.commit()
        log.info("card deleted user=%s card=%s", user_id, card_id)
