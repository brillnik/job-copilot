"""Where the apply worker may go: a hostname allow-policy plus the site rules.

The Playwright worker installs `HostPolicy` as a route handler on its browser context:
every request whose host is not the target host, our API host or a known ATS suffix is
aborted. wellfound.com, naukri.com, hiring.cafe and linkedin.com are never allowed.
"""

import ipaddress
from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.core.config import settings
from app.core.netguard import is_denied

# Sites handled by the browser extension only (the server never opens them).
EXTENSION_SITES = {
    "wellfound.com": "wellfound",
    "naukri.com": "naukri",
    "hiring.cafe": "hiring_cafe",
}
# Reasons that count towards auto-pausing a site (warning pages and blocks).
BLOCK_REASONS = frozenset({"captcha", "login", "verification", "bot_check", "blocked"})


class BlockedTarget(Exception):
    """The worker refuses to open this URL; `reason` is a short code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower().rstrip(".")


def _matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def extension_site(url: str) -> str | None:
    host = host_of(url)
    for domain, site in EXTENSION_SITES.items():
        if _matches(host, domain):
            return site
    return None


def is_linkedin(url: str) -> bool:
    return _matches(host_of(url), "linkedin.com")


def is_private_host(host: str) -> bool:
    if host in ("localhost", "") or host.endswith(
        (".local", ".internal", ".localhost")
    ):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return not ip.is_global


def check_target(url: str, *, allow_private: bool | None = None) -> None:
    """Raise BlockedTarget unless the worker may open `url`."""
    allow_private = (
        settings.apply_allow_private_hosts if allow_private is None else allow_private
    )
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise BlockedTarget("bad_url")
    if is_denied(url):  # wellfound, naukri, hiring.cafe, linkedin
        raise BlockedTarget("denied_site")
    if not allow_private and is_private_host(host_of(url)):
        raise BlockedTarget("private_host")


@dataclass
class HostPolicy:
    target_host: str
    api_host: str | None = None
    ats_suffixes: tuple[str, ...] = ()
    allow_private: bool = False
    blocked: list[str] = field(default_factory=list)  # hosts refused (no paths)
    violations: list[str] = field(default_factory=list)  # hosts the browser contacted

    @classmethod
    def for_target(cls, url: str) -> "HostPolicy":
        check_target(url)
        return cls(
            target_host=host_of(url),
            api_host=host_of(settings.public_base_url) or None,
            ats_suffixes=tuple(settings.apply_ats_host_suffixes),
            allow_private=settings.apply_allow_private_hosts,
        )

    def allows(self, url: str) -> bool:
        if url.startswith(("about:", "data:", "blob:")):
            return True
        p = urlparse(url)
        host = (p.hostname or "").lower().rstrip(".")
        if p.scheme not in ("http", "https") or not host:
            return False
        if is_denied(url):
            return False
        if host in (self.target_host, self.api_host):
            return self.allow_private or not is_private_host(host)
        if is_private_host(host):
            return False
        return any(_matches(host, s) for s in self.ats_suffixes)

    def observe(self, url: str) -> None:
        """page.on('request'): sees EVERY request, redirect hops included (the route
        handler does not see redirects), so a foreign hop is recorded and the run halts."""
        if not self.allows(url):
            self.violations.append(host_of(url))

    def resolver_rules(self) -> str:
        """Chrome --host-resolver-rules: DNS for every other host fails, which also
        stops redirects the route handler cannot see. (Chrome launched by us only.)"""
        hosts = [h for h in (self.target_host, self.api_host) if h]
        hosts += [f"*.{s}" for s in self.ats_suffixes] + list(self.ats_suffixes)
        return "MAP * ~NOTFOUND , " + " , ".join(f"EXCLUDE {h}" for h in hosts)

    def handle(self, route) -> None:
        """Playwright route handler: continue allowed requests, abort the rest."""
        url = route.request.url
        if self.allows(url):
            route.continue_()
            return
        self.blocked.append(host_of(url))
        route.abort("blockedbyclient")
