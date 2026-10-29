import os
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-root env files are the source of truth (shared with apps/web).
# Later files win: root .env < root .env.<APP_ENV> < apps/api/.env
ROOT = Path(__file__).resolve().parents[4]
APP_ENV = os.environ.get("APP_ENV", "local")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", ROOT / f".env.{APP_ENV}", ".env"),
        extra="ignore",
    )

    cors_origins: list[str] = ["http://localhost:3000"]

    # SQLite for local dev; use e.g. postgresql+psycopg://user:pass@host/db elsewhere
    database_url: str = f"sqlite:///{ROOT / 'apps' / 'api' / 'job_copilot.db'}"

    # Document storage. "local" writes to upload_dir; "s3" uses any S3-compatible
    # store (MinIO locally). Leave s3_endpoint_url empty for real AWS S3.
    storage_backend: Literal["local", "s3"] = "local"
    s3_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "job-copilot"
    s3_region: str = "us-east-1"

    # Resume uploads
    upload_dir: Path = ROOT / "apps" / "api" / "uploads"
    max_resume_bytes: int = 5 * 1024 * 1024

    # Auth0 (AUTH0_DOMAIN / AUTH0_AUDIENCE): domain without https://
    auth0_domain: str = ""
    auth0_audience: str = ""
    # Access tokens carry no email/name unless an Auth0 Action adds them; custom
    # claims must be namespaced, e.g. "https://jobcopilot.app/email".
    auth0_email_claim: str = "email"
    auth0_name_claim: str = "name"


settings = Settings()
