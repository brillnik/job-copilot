"""BrowserDriver: how the engine gets a page. Real Chrome in production, fakes in tests.

DEVIATION from the original spec ("headless per task, no persistent profile"): the user
wants portal login sessions to exist, so the driver uses their LOCAL Google Chrome with
a DEDICATED profile directory (never the default profile):

- APPLY_BROWSER_MODE=cdp (default): connect_over_cdp to a Chrome the user started with
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \\
      --remote-debugging-port=9222 --user-data-dir=$HOME/.job-copilot-chrome
  (APPLY_CDP_URL, default http://127.0.0.1:9222). We open one tab, and close only it.
- APPLY_BROWSER_MODE=chrome: Playwright launches channel="chrome" with a persistent
  context in APPLY_CHROME_USER_DATA_DIR.
APPLY_HEADLESS picks headless or headed. A session may exist, but a login wall,
CAPTCHA or verification page still stops the application (never bypassed). The
HostPolicy route handler is installed on OUR page/context in both modes. Cookies and
storage are never read, copied, exported or logged here.
"""

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any, Protocol

from app.apply.policy import HostPolicy
from app.core.config import settings


class BrowserDriver(Protocol):
    def session(self, policy: HostPolicy) -> AbstractContextManager[Any]:
        """A context manager yielding a page for one application."""
        ...


class ChromeUnavailable(Exception):
    pass


class PlaywrightDriver:
    def __init__(
        self,
        mode: str | None = None,
        *,
        cdp_url: str | None = None,
        user_data_dir: str | None = None,
        headless: bool | None = None,
    ) -> None:
        self.mode = mode or settings.apply_browser_mode
        self.cdp_url = cdp_url or settings.apply_cdp_url
        self.user_data_dir = user_data_dir or settings.apply_chrome_user_data_dir
        self.headless = settings.apply_headless if headless is None else headless

    @contextmanager
    def session(self, policy: HostPolicy) -> Iterator[Any]:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            if self.mode == "cdp":
                try:
                    browser = pw.chromium.connect_over_cdp(self.cdp_url)
                except Exception as e:  # noqa: BLE001
                    raise ChromeUnavailable(f"cdp:{type(e).__name__}") from None
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
                page = ctx.new_page()
                page.route("**/*", policy.handle)  # only our tab, not the user's others
                page.set_default_timeout(settings.apply_nav_timeout_ms)
                try:
                    yield page
                finally:
                    page.close()  # leave the user's Chrome running
                return
            if not self.user_data_dir:
                raise ChromeUnavailable("APPLY_CHROME_USER_DATA_DIR is not set")
            try:
                ctx = pw.chromium.launch_persistent_context(
                    self.user_data_dir,
                    channel="chrome",
                    headless=self.headless,
                    accept_downloads=False,
                    service_workers="block",
                    viewport={"width": 1280, "height": 1600},
                    args=[f"--host-resolver-rules={policy.resolver_rules()}"],
                )
            except Exception as e:  # noqa: BLE001
                raise ChromeUnavailable(f"chrome:{type(e).__name__}") from None
            try:
                ctx.route("**/*", policy.handle)
                page = ctx.new_page()
                page.set_default_timeout(settings.apply_nav_timeout_ms)
                page.set_default_navigation_timeout(settings.apply_nav_timeout_ms)
                yield page
            finally:
                ctx.close()
