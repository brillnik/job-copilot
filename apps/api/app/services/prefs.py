from app.core.config import settings
from app.models.user import User
from app.schemas.account import PreferencesOut


def default_preferences() -> dict:
    return {
        "target_roles": [],
        "cities": [],
        "current_ctc_lpa": 0.0,
        "expected_ctc_lpa": 0.0,
        "notice_days": 0,
        "default_length": "auto",
        "template": "classic",
        "daily_cap": settings.daily_run_cap,
        "coverage_target": 0.6,
        "theme": "system",
    }


def preferences_of(user: User | None) -> PreferencesOut:
    """Stored preferences over the defaults; tolerant of fields a later version adds."""
    stored = (user.preferences if user else None) or {}
    merged = default_preferences() | {
        k: v for k, v in stored.items() if k in PreferencesOut.model_fields
    }
    return PreferencesOut.model_validate(merged)
