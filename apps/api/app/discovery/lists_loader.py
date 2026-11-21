"""Company list files (discovery/lists/*.yaml) -> companies table."""

import logging
import re
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovery import Company

log = logging.getLogger(__name__)
LISTS_DIR = Path(__file__).parent / "lists"


def name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def load_list_file(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text()) or {}
    return [c for c in data.get("companies", []) if c.get("name")]


def sync_lists(session: Session, directory: Path = LISTS_DIR) -> int:
    """Upsert every listed company and tag it with its list. Idempotent."""
    count = 0
    for path in sorted(directory.glob("*.yaml")):
        tag = path.stem
        for entry in load_list_file(path):
            key = name_key(entry["name"])
            row = session.scalar(select(Company).where(Company.name_key == key))
            if row is None:
                row = Company(
                    name=entry["name"],
                    name_key=key,
                    careers_url=entry.get("careers_url"),
                    lists=[tag],
                )
                session.add(row)
            else:
                if tag not in (row.lists or []):
                    row.lists = [*(row.lists or []), tag]
                if entry.get("careers_url") and not row.careers_url:
                    row.careers_url = entry["careers_url"]
            count += 1
        session.flush()
    session.commit()
    log.info("lists synced companies=%d", count)
    return count
