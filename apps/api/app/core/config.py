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

    # LOG_LEVEL: DEBUG | INFO | WARNING | ERROR. LOG_SQL=true echoes every SQL statement.
    log_level: str = "INFO"
    log_sql: bool = False

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
    max_image_bytes: int = 5 * 1024 * 1024

    # Bullet retrieval. "fastembed" is semantic (local ONNX model, downloaded on first
    # use); "hashing" is keyword-only and needs no download.
    embedding_backend: Literal["fastembed", "hashing"] = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # Which model extracts resumes and job postings: "qwen" (Qwen3-VL on a local
    # Ollama server) or "claude" (Anthropic API).
    ai_provider: Literal["qwen", "claude"] = "qwen"

    # Qwen3-VL via Ollama: `ollama pull qwen3-vl:8b-instruct`, then `ollama serve`.
    # Use an -instruct tag: the plain `qwen3-vl:8b` tag is the thinking variant, which
    # spends its whole token budget reasoning and returns empty content.
    qwen_base_url: str = "http://localhost:11434"
    qwen_model: str = "qwen3-vl:8b-instruct"
    qwen_timeout_s: float = 300.0  # local inference is slow, especially on page images
    qwen_num_ctx: int = 16384  # Ollama's default (4096) silently truncates a resume
    qwen_max_pdf_pages: int = 3  # scanned PDFs only: pages rasterised for the model
    qwen_pdf_scale: float = 1.5  # render scale for those pages (1.0 = 72 dpi)

    # Claude vision extracts a draft profile from an uploaded resume.
    anthropic_api_key: str = ""
    extraction_model: str = "claude-sonnet-5-5"

    # Jobs
    jobs_per_hour: int = 30  # per-user cap on POST /jobs (new jobs, not duplicates)
    daily_run_cap: int = 10  # tailoring runs per user per day (resets midnight IST)
    day_timezone: str = "Asia/Kolkata"
    # Posts on these domains sit behind a login, so we never fetch them.
    login_walled_domains: list[str] = [
        "linkedin.com",
        "naukri.com",
        "indeed.com",
        "glassdoor.com",
        "instahyre.com",
    ]
    fetch_timeout_s: float = 10.0
    fetch_max_bytes: int = 2 * 1024 * 1024
    fetch_max_redirects: int = 5
    min_page_chars: int = 300  # shorter fetched pages are treated as failed fetches
    job_task_retries: int = 2
    job_task_backoff_s: float = 2.0
    jd_extraction_model: str = "claude-sonnet-5-5"

    # Match scoring (weights sum to 1.0)
    w_must: float = 0.60
    w_experience: float = 0.15
    w_location: float = 0.10
    w_ctc: float = 0.10
    w_nice: float = 0.05
    evidence_min_score: float = (
        0.45  # vector similarity needed to count a bullet as proof
    )
    ask_credit: float = (
        0.5  # share of a must-have credited when the user can plausibly confirm
    )
    neutral_fit: float = 0.5  # fit assumed when the JD or the user gives no information
    overqualified_fit: float = 0.8
    # skill -> adjacent skills that make "ask the user" plausible
    skill_adjacency: dict[str, list[str]] = {
        "kafka": ["rabbitmq", "kinesis", "pulsar", "sqs"],
        "postgresql": ["mysql", "sql"],
        "mysql": ["postgresql", "sql"],
        "aws": ["gcp", "azure"],
        "gcp": ["aws", "azure"],
        "azure": ["aws", "gcp"],
        "kubernetes": ["docker", "ecs"],
        "react": ["vue", "angular", "next.js"],
        "python": ["django", "flask", "fastapi"],
        "java": ["kotlin", "spring"],
        "terraform": ["cloudformation", "pulumi"],
    }
    # canonical skill -> aliases
    skill_synonyms: dict[str, list[str]] = {
        "javascript": ["js", "ecmascript"],
        "typescript": ["ts"],
        "postgresql": ["postgres", "psql"],
        "kubernetes": ["k8s"],
        "golang": ["go"],
        "node.js": ["node", "nodejs"],
        "machine learning": ["ml"],
        "amazon web services": ["aws"],
        "ci/cd": ["cicd", "continuous integration"],
    }

    # Auth0 (AUTH0_DOMAIN / AUTH0_AUDIENCE): domain without https://
    auth0_domain: str = ""
    auth0_audience: str = ""
    # Access tokens carry no email/name unless an Auth0 Action adds them; custom
    # claims must be namespaced, e.g. "https://jobcopilot.app/email".
    auth0_email_claim: str = "email"
    auth0_name_claim: str = "name"


settings = Settings()
