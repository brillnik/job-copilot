from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Column = Literal["approved", "applied", "response", "interview", "offer", "rejected"]


class ConnectOut(BaseModel):
    url: str  # send the browser here; Google redirects back to /callback


class GmailStatus(BaseModel):
    enabled: bool  # feature flag for this user
    connected: bool
    needs_reconnect: bool = False
    connected_at: datetime | None = None
    last_synced_at: datetime | None = None
    pending_suggestions: int = 0


class ConnectedOut(BaseModel):
    connected: bool = True


class Suggestion(BaseModel):
    id: str
    job_id: str | None
    company: str | None
    title: str | None
    classification: str
    confidence: float
    suggested_column: Column
    status: Literal["pending", "accepted", "dismissed"]
    received_at: datetime


class PushMessage(BaseModel):
    data: str = ""
    messageId: str | None = None


class PushEnvelope(BaseModel):
    message: PushMessage
    subscription: str | None = None
