"""Proof of an application: screenshots under users/{user_id}/applications/{id}/."""

import uuid

from app.storage.base import Storage


def proof_key(user_id: uuid.UUID, application_id: str, name: str) -> str:
    return f"users/{user_id.hex}/applications/{application_id}/{name}.png"


def save_screenshot(
    storage: Storage, user_id: uuid.UUID, application_id: str, name: str, png: bytes
) -> str:
    key = proof_key(user_id, application_id, name)
    storage.save(key, png)
    return key
