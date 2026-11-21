"""Google OAuth and Gmail REST access over httpx, behind an injectable Protocol.

Only headers and a short snippet are ever requested; message bodies are never
fetched. Nothing here logs addresses, subjects or tokens.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parseaddr
from typing import Protocol
from urllib.parse import urlencode

import httpx

log = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class GoogleError(Exception):
    """A failure worth retrying later (network, 5xx, rate limit)."""


class GoogleAuthError(GoogleError):
    """The grant is gone (revoked or expired): the user must reconnect."""


class HistoryExpired(GoogleError):
    """The stored historyId is too old; fall back to a messages list."""


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str | None


@dataclass(frozen=True)
class MailboxProfile:
    email: str
    history_id: str | None


@dataclass(frozen=True)
class MessageMeta:
    id: str
    sender_domain: str
    subject: str
    snippet: str
    received_at: datetime


@dataclass(frozen=True)
class MessageIds:
    ids: list[str]
    history_id: str | None


class GoogleClient(Protocol):
    def exchange_code(self, code: str) -> TokenSet: ...
    def refresh_access_token(self, refresh_token: str) -> str: ...
    def profile(self, access_token: str) -> MailboxProfile: ...
    def watch(self, access_token: str, topic: str) -> None: ...
    def list_history(self, access_token: str, start_history_id: str) -> MessageIds: ...
    def list_messages(self, access_token: str, query: str, limit: int) -> list[str]: ...
    def get_metadata(self, access_token: str, message_id: str) -> MessageMeta: ...
    def revoke(self, token: str) -> None: ...


def authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    return (
        AUTH_URL
        + "?"
        + urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": SCOPE,
                "access_type": "offline",
                "prompt": "consent",  # Google only re-issues a refresh token on consent
                "include_granted_scopes": "false",
                "state": state,
            }
        )
    )


def sender_domain(from_header: str) -> str:
    addr = parseaddr(from_header)[1].lower()
    return addr.rsplit("@", 1)[1] if "@" in addr else ""


class HttpGoogleClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        snippet_chars: int = 240,
        http: httpx.Client | None = None,
    ) -> None:
        self.client_id, self.client_secret = client_id, client_secret
        self.redirect_uri, self.snippet_chars = redirect_uri, snippet_chars
        self.http = http or httpx.Client(timeout=15.0)

    # --- plumbing ---------------------------------------------------------------
    def _send(self, method: str, url: str, **kw) -> dict:
        try:
            r = self.http.request(method, url, **kw)
        except httpx.HTTPError as e:
            raise GoogleError(type(e).__name__) from None
        if r.status_code in (400, 401) and "invalid_grant" in r.text:
            raise GoogleAuthError("invalid_grant")
        if r.status_code == 401:
            raise GoogleAuthError("unauthorized")
        if r.status_code == 404 and "/history" in url:
            raise HistoryExpired()
        if r.status_code >= 400:
            log.warning("google call failed status=%d", r.status_code)
            raise GoogleError(f"http_{r.status_code}")
        return r.json() if r.content else {}

    @staticmethod
    def _auth(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    # --- oauth ------------------------------------------------------------------
    def exchange_code(self, code: str) -> TokenSet:
        data = self._send(
            "POST",
            TOKEN_URL,
            data={
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        return TokenSet(data["access_token"], data.get("refresh_token"))

    def refresh_access_token(self, refresh_token: str) -> str:
        data = self._send(
            "POST",
            TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
            },
        )
        return data["access_token"]

    def revoke(self, token: str) -> None:
        self._send("POST", REVOKE_URL, data={"token": token})

    # --- gmail ------------------------------------------------------------------
    def profile(self, access_token: str) -> MailboxProfile:
        d = self._send("GET", f"{GMAIL}/profile", headers=self._auth(access_token))
        return MailboxProfile(d["emailAddress"], str(d.get("historyId") or "") or None)

    def watch(self, access_token: str, topic: str) -> None:
        self._send(
            "POST",
            f"{GMAIL}/watch",
            headers=self._auth(access_token),
            json={"topicName": topic, "labelIds": ["INBOX"]},
        )

    def list_history(self, access_token: str, start_history_id: str) -> MessageIds:
        ids: list[str] = []
        latest: str | None = None
        page: str | None = None
        while True:
            params = {
                "startHistoryId": start_history_id,
                "historyTypes": "messageAdded",
            }
            if page:
                params["pageToken"] = page
            d = self._send(
                "GET",
                f"{GMAIL}/history",
                headers=self._auth(access_token),
                params=params,
            )
            latest = str(d.get("historyId") or latest or "") or None
            for h in d.get("history", []):
                for m in h.get("messagesAdded", []):
                    mid = m["message"]["id"]
                    if mid not in ids:
                        ids.append(mid)
            page = d.get("nextPageToken")
            if not page:
                return MessageIds(ids, latest)

    def list_messages(self, access_token: str, query: str, limit: int) -> list[str]:
        d = self._send(
            "GET",
            f"{GMAIL}/messages",
            headers=self._auth(access_token),
            params={"q": query, "maxResults": limit},
        )
        return [m["id"] for m in d.get("messages", [])]

    def get_metadata(self, access_token: str, message_id: str) -> MessageMeta:
        d = self._send(
            "GET",
            f"{GMAIL}/messages/{message_id}",
            headers=self._auth(access_token),
            params=[
                ("format", "metadata"),
                ("metadataHeaders", "From"),
                ("metadataHeaders", "Subject"),
                ("metadataHeaders", "Date"),
            ],
        )
        headers = {
            h["name"].lower(): h["value"]
            for h in d.get("payload", {}).get("headers", [])
        }
        ms = int(d.get("internalDate") or 0)
        return MessageMeta(
            id=d["id"],
            sender_domain=sender_domain(headers.get("from", "")),
            subject=headers.get("subject", ""),
            snippet=(d.get("snippet") or "")[: self.snippet_chars],
            received_at=datetime.fromtimestamp(ms / 1000, UTC),
        )
