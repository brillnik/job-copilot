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
    daily_cap_max: int = 50  # ceiling for a user's own daily_cap preference
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

    # Runs
    max_tailor_iterations: int = 3
    sse_heartbeat_s: float = 15.0
    sse_poll_s: float = 0.5  # how often a stream checks the database for new events
    signed_url_ttl_s: int = 300  # run PDFs; hard ceiling is 5 minutes
    signing_secret: str = "dev-only-change-me"  # HMAC key for signed URLs
    public_base_url: str = ""  # prefix for signed links; empty = same origin

    # Tailoring agent (LangGraph). "none" leaves runs queued (no agent wired).
    tailor_agent: Literal["none", "graph"] = "none"
    tailor_model: str = "claude-sonnet-5-5"
    tailor_checkpoint_path: str = str(ROOT / "apps" / "api" / "tailor_checkpoints.db")
    # Past approved resumes as STYLE examples. A/B: users whose hash falls under
    # tailor_examples_ab_pct (0-100) get examples; the rest never do.
    tailor_examples_enabled: bool = False
    tailor_examples_ab_pct: int = 50
    tailor_examples_min_sim: float = 0.6
    tailor_examples_max: int = 3

    # Screening-answer bank
    screening_model: str = "claude-sonnet-5-5"
    screening_min_sim: float = 0.85  # saved answer reused only at/above this similarity

    # Settings
    allowed_cities: list[str] = [
        "Remote", "Bengaluru", "Hyderabad", "Pune", "Mumbai", "Delhi NCR",
        "Chennai", "Kolkata", "Ahmedabad", "Kochi", "Jaipur", "Chandigarh",
    ]  # fmt: skip

    # Account
    policy_version: str = "2026-01"
    reauth_window_s: int = 600  # DELETE /me needs a sign-in this recent
    export_ttl_days: int = 7
    export_link_ttl_s: int = 24 * 3600
    # Fernet key for export archives (urlsafe base64, 32 bytes). Empty = derived
    # from signing_secret, which is fine for dev only.
    export_encryption_key: str = ""

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

    # --- Gmail reply tracking (phase 4) ---------------------------------------
    # Test users only until Google's app verification passes: the feature is on for
    # everyone with GMAIL_FEATURE=true, otherwise only for the user ids listed in
    # GMAIL_ENABLED_USERS (JSON list of user UUIDs).
    gmail_feature: bool = False
    gmail_enabled_users: list[str] = []
    google_client_id: str = ""
    google_client_secret: str = ""
    gmail_redirect_uri: str = (
        ""  # must match the OAuth client, e.g. {api}/integrations/gmail/callback
    )
    gmail_post_connect_url: str = ""  # if set, the callback redirects the browser here
    gmail_state_ttl_s: int = 600
    # Pub/Sub push: the push subscription URL carries ?token=<this>. Empty rejects all.
    gmail_push_secret: str = ""
    gmail_pubsub_topic: str = ""  # projects/<p>/topics/<t>; empty = poll only
    gmail_backfill_days: int = 7  # first sync looks this far back
    gmail_max_messages: int = 50  # per sync
    gmail_auto_threshold: float = 0.8  # >= moves the card; lower becomes a suggestion
    gmail_suggest_min: float = 0.4  # below this nothing is suggested
    gmail_snippet_chars: int = 240  # what the classifier sees; never persisted
    gmail_classifier_model: str = "claude-haiku-5-5"
    gmail_ats_domains: list[str] = [
        "greenhouse.io", "greenhouse-mail.io", "hire.lever.co", "lever.co",
        "ashbyhq.com", "myworkday.com", "workday.com", "smartrecruiters.com",
        "icims.com", "jobvite.com", "bamboohr.com", "recruitee.com",
        "workable.com", "breezy.hr", "teamtailor.com",
    ]  # fmt: skip

    # --- Fine-tuned extractor (phase 5) ---------------------------------------
    # EXTRACTOR_BACKEND: unset = follow ai_provider (unchanged behaviour);
    # claude = Claude only; shadow = run local too, return Claude's result and record
    # a per-field comparison; local = use the local model, fall back to Claude.
    extractor_backend: Literal["claude", "shadow", "local"] | None = None
    # OpenAI-compatible vLLM endpoint, e.g. http://localhost:8000 (/v1 is appended).
    local_extractor_url: str = ""
    local_extractor_model: str = "job-copilot-extractor"
    local_extractor_api_key: str = ""
    local_extractor_timeout_s: float = 60.0
    # Training dataset snapshots live under this storage prefix (never users/{id}/).
    training_snapshot_prefix: str = "snapshots"

    # --- Discovery & recommendations (v2 phase 1) ---------------------------------
    discovery_sync_cron: str = (
        "30 2 * * *"  # daily pipeline; evaluated in discovery_timezone
    )
    discovery_timezone: str = "Asia/Kolkata"
    discovery_user_agent: str = (
        "JobCopilotBot/1.0 (+job discovery; respects robots.txt)"
    )
    discovery_http_timeout_s: float = 10.0
    discovery_max_retries: int = 3
    discovery_backoff_s: float = 1.0
    discovery_host_concurrency: int = 2  # simultaneous requests per host
    discovery_workers: int = 4  # fan-out threads for sync_source
    discovery_max_pages: int = (
        25  # pages per source per run (20 jobs/page on Himalayas)
    )
    discovery_max_extractions_per_run: int = 500  # shared extract_jd budget per run
    discovery_close_after_days: int = 3  # not seen this long -> is_open check
    discovery_dedupe_window_days: int = 30
    discovery_redetect_days: int = 30  # re-run ATS detection monthly
    himalayas_api_key: str = ""  # optional Bearer token
    himalayas_base_url: str = "https://himalayas.app"
    himalayas_country: str = "India"
    himalayas_query: str = ""
    # Recommendations
    reco_candidates_k: int = 200
    reco_max_age_days: int = 21
    reco_digest_size: int = 10
    reco_user_country: str = (
        "India"  # remote jobs restricted to other countries are dropped
    )
    # Browser extension
    extension_pair_code_ttl_s: int = 600
    extension_pair_attempts_per_min: int = 10

    # --- Auto-apply and Autopilot (v2 phase 3) -------------------------------------
    # Global kill switch and the ATS adapters allowed to submit. "generic" enables the
    # unknown-form fallback, which is conservative and off by default.
    apply_enabled: bool = True
    apply_enabled_ats: list[str] = ["greenhouse", "lever", "ashby"]
    # "external": the API only queues; the separate apply container (python -m
    # app.apply.worker serve) claims queued rows. "inprocess": the API runs them itself.
    apply_worker_mode: Literal["inprocess", "external"] = "external"
    apply_workers: int = 1
    apply_poll_s: float = 5.0
    # Browser: the user's LOCAL Google Chrome with a dedicated, logged-in profile.
    # "cdp": connect_over_cdp to a Chrome started with --remote-debugging-port
    # (APPLY_CDP_URL); "chrome": Playwright launches channel="chrome" with the dedicated
    # APPLY_CHROME_USER_DATA_DIR (never the default profile). Cookies/storage are
    # never read, copied, exported or logged by this code.
    apply_browser_mode: Literal["cdp", "chrome"] = "cdp"
    apply_cdp_url: str = "http://127.0.0.1:9222"
    apply_chrome_user_data_dir: str = ""
    apply_headless: bool = False
    apply_nav_timeout_ms: int = 20000
    apply_run_timeout_s: int = 180
    # Never True in production: lets the worker open loopback/private addresses.
    apply_allow_private_hosts: bool = False
    # Hosts the worker may follow redirects to (an ATS an employer page hands off to).
    apply_ats_host_suffixes: list[str] = [
        "greenhouse.io", "lever.co", "ashbyhq.com", "himalayas.app",
    ]  # fmt: skip
    apply_fallback_min_confidence: float = 0.9
    autopilot_policy_version: str = "2026-11"
    autopilot_default_min_score: int = 75
    autopilot_default_daily_cap: int = 15
    autopilot_daily_cap_max: int = 50
    autopilot_default_digest_time: str = "19:00"  # day_timezone (Asia/Kolkata)
    # Random pause between browser actions, milliseconds (min, max).
    autopilot_pacing_ms: list[int] = [800, 2500]
    autopilot_site_caps: dict[str, int] = {
        "wellfound": 5,
        "naukri": 5,
        "hiring_cafe": 5,
    }
    autopilot_default_site_cap: int = 15
    autopilot_ats_hourly_cap: int = 30  # per ATS, across all users
    autopilot_pause_after_blocks: int = 2  # consecutive blocks before a site pauses
    autopilot_max_saves_per_tick: int = 10
    # Required canonical fields per extension site; the extension may add more.
    extension_required_fields: dict[str, list[str]] = {
        "wellfound": ["name", "email", "resume"],
        "naukri": ["name", "email", "phone", "resume"],
        "hiring_cafe": ["name", "email", "resume"],
    }
    extension_max_screenshot_bytes: int = 3 * 1024 * 1024


settings = Settings()
