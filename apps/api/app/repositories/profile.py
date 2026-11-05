import uuid

from sqlalchemy import func, select

from app.models.profile import APPROVED, DRAFT, Profile, ProfileBullet
from app.repositories.base import BaseRepository


class ProfileRepository(BaseRepository[Profile]):
    model = Profile

    def get_draft(self, user_id: uuid.UUID) -> Profile | None:
        return self.session.scalar(
            select(Profile).where(Profile.user_id == user_id, Profile.status == DRAFT)
        )

    def get_latest_approved(self, user_id: uuid.UUID) -> Profile | None:
        return self.session.scalar(
            select(Profile)
            .where(Profile.user_id == user_id, Profile.status == APPROVED)
            .order_by(Profile.version.desc())
            .limit(1)
        )

    def next_version(self, user_id: uuid.UUID) -> int:
        current = self.session.scalar(
            select(func.max(Profile.version)).where(Profile.user_id == user_id)
        )
        return (current or 0) + 1

    def bullets_for(self, profile_id: str) -> list[ProfileBullet]:
        return list(
            self.session.scalars(
                select(ProfileBullet).where(ProfileBullet.profile_id == profile_id)
            )
        )

    def add_bullets(self, bullets: list[ProfileBullet]) -> None:
        self.session.add_all(bullets)
        self.session.commit()

    def approve(
        self, profile: Profile, version: int, approved_at, bullets: list[ProfileBullet]
    ) -> Profile:
        """Promote a draft and index its bullets in a single transaction."""
        profile.status = APPROVED
        profile.version = version
        profile.approved_at = approved_at
        self.session.add_all(bullets)
        self.session.commit()
        return profile
