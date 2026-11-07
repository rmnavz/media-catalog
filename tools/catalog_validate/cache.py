from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class IdCache:
    def __init__(self, path: Path, *, ttl_days: int = 30) -> None:
        self.path = path
        self.ttl_days = ttl_days
        self.data: dict[str, Any] = {"version": 1, "entries": {}}
        self._dirty = False
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and isinstance(loaded.get("entries"), dict):
                    self.data = loaded
            except (OSError, json.JSONDecodeError):
                pass

    @property
    def entries(self) -> dict[str, Any]:
        return self.data.setdefault("entries", {})

    def get(self, key: str, *, refresh: bool = False) -> dict[str, Any] | None:
        if refresh:
            return None
        entry = self.entries.get(key)
        if not isinstance(entry, dict):
            return None
        checked = parse_ts(entry.get("checked_at"))
        if checked is None:
            return None
        age_days = (utc_now() - checked).total_seconds() / 86400
        if age_days > self.ttl_days:
            return None
        return entry

    def set(self, key: str, entry: dict[str, Any]) -> None:
        payload = dict(entry)
        payload.setdefault("checked_at", utc_now().isoformat())
        self.entries[key] = payload
        self._dirty = True

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self._dirty = False
