"""Detect pages we must stop on. We never solve, wait out or bypass any of them.

Works on a small page surface (url, content(), inner_text(), frames) so unit tests can
use a fake page and the worker a real Playwright page.
"""

import re
from dataclasses import dataclass

# kind -> short reason stored as skip_reason. kinds in policy.BLOCK_REASONS count towards
# a site auto-pause.
CAPTCHA_FRAMES = (
    "recaptcha",
    "hcaptcha",
    "turnstile",
    "challenges.cloudflare",
    "arkoselabs",
    "funcaptcha",
    "captcha",
)
CAPTCHA_HTML = (
    "g-recaptcha", "grecaptcha", "h-captcha", "hcaptcha.com", "cf-turnstile",
    "challenges.cloudflare.com", "arkoselabs", "funcaptcha", "recaptcha/api",
    "data-sitekey",
)  # fmt: skip
BOT_TEXT = (
    "unusual activity", "unusual traffic", "verify you are human",
    "verify you are a human", "are you a robot", "are you human",
    "checking your browser", "just a moment", "access denied", "request blocked",
    "bot detected", "press & hold", "automated queries", "suspicious activity",
)  # fmt: skip
VERIFY_TEXT = (
    "verify your email", "verification code", "enter the code", "we sent a code",
    "we've sent a code", "one-time password", "confirm your email",
    "verify your phone", "sms code", "check your email for a",
)  # fmt: skip
VERIFY_RE = re.compile(r"\botp\b")
LOGIN_TEXT = (
    "sign in to apply", "log in to apply", "login to apply", "sign in to continue",
    "log in to continue", "login to continue", "please log in", "please sign in",
    "create an account to apply", "sign in to your account",
)  # fmt: skip


@dataclass(frozen=True)
class Blocker:
    kind: str  # captcha | login | verification | bot_check | layout_change
    detail: str = ""

    @property
    def reason(self) -> str:
        return self.kind


def _safe(fn, default=""):
    try:
        return fn()
    except Exception:  # noqa: BLE001 - a page mid-navigation must not crash detection
        return default


def detect_blockers(page) -> Blocker | None:
    html = str(_safe(page.content)).lower()
    text = str(_safe(lambda: page.inner_text("body"))).lower()
    frames = [
        str(_safe(lambda f=f: f.url)).lower()
        for f in _safe(lambda: list(page.frames), [])
    ]
    url = str(_safe(lambda: page.url)).lower()

    if any(t in text for t in BOT_TEXT):
        return Blocker("bot_check", "page text")
    if any(any(t in u for t in CAPTCHA_FRAMES) for u in frames) or any(
        t in html for t in CAPTCHA_HTML
    ):
        return Blocker("captcha", "captcha widget")
    if any(t in text for t in VERIFY_TEXT) or VERIFY_RE.search(text):
        return Blocker("verification", "verification prompt")
    has_password = (
        'type="password"' in html
        or "type=password" in html
        or "type='password'" in html
    )
    if has_password or any(t in text for t in LOGIN_TEXT):
        return Blocker("login", "login wall")
    if any(seg in url for seg in ("/login", "/signin", "/sign-in", "/sso")):
        return Blocker("login", "login url")
    return None
