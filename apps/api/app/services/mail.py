import logging
from typing import Protocol

log = logging.getLogger(__name__)


class Mailer(Protocol):
    def send(self, user_id: str, template: str, **params: str) -> None: ...


class LogMailer:
    """Placeholder until an email provider is wired. Logs the template, never the address."""

    def send(self, user_id: str, template: str, **params: str) -> None:
        log.info("mail (not sent: no provider) user=%s template=%s", user_id, template)
