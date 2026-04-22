"""
Profile persistence.

One JSON file per profile, stored in a directory. Kept this way (rather than
a single big JSON or SQLite) so the launcher can watch the dir for changes
and so users can hand-edit / version-control individual profiles.

Layout:
    <root>/
        profiles/
            <id>.json
        index.json         # id -> {name, tags, last_used_at, use_count, archetype_id}

The index is a denormalized cache for fast listing without opening every file.
It's rebuildable at any time via ProfileStore.rebuild_index().
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from fpgen.profile import Profile


INDEX_FILENAME = "index.json"
PROFILES_DIRNAME = "profiles"


class ProfileStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser()
        self.profiles_dir = self.root / PROFILES_DIRNAME
        self.index_path = self.root / INDEX_FILENAME
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._write_index({})

    # --- index ---

    def _read_index(self) -> Dict[str, Dict]:
        try:
            with self.index_path.open() as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write_index(self, idx: Dict[str, Dict]) -> None:
        tmp = self.index_path.with_suffix(".json.tmp")
        with tmp.open("w") as f:
            json.dump(idx, f, indent=2, sort_keys=True)
        os.replace(tmp, self.index_path)

    def _index_entry(self, p: Profile) -> Dict:
        return {
            "name": p.name,
            "archetype_id": p.archetype_id,
            "tags": list(p.tags),
            "last_used_at": p.last_used_at,
            "use_count": p.use_count,
            "created_at": p.created_at,
            "proxy_id": p.proxy_id,
            "os": p.os,
            "locale": p.locale,
        }

    # --- CRUD ---

    def _profile_path(self, profile_id: str) -> Path:
        return self.profiles_dir / f"{profile_id}.json"

    def save(self, p: Profile) -> None:
        path = self._profile_path(p.id)
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w") as f:
            f.write(p.to_json())
        os.replace(tmp, path)
        idx = self._read_index()
        idx[p.id] = self._index_entry(p)
        self._write_index(idx)

    def load(self, profile_id: str) -> Profile:
        path = self._profile_path(profile_id)
        if not path.exists():
            raise KeyError(f"profile not found: {profile_id}")
        with path.open() as f:
            return Profile.from_json(f.read())

    def exists(self, profile_id: str) -> bool:
        return self._profile_path(profile_id).exists()

    def delete(self, profile_id: str) -> None:
        path = self._profile_path(profile_id)
        if path.exists():
            path.unlink()
        idx = self._read_index()
        idx.pop(profile_id, None)
        self._write_index(idx)

    def list(self, tag: Optional[str] = None, os: Optional[str] = None) -> List[Dict]:
        """Return index entries (cheap; doesn't load full profiles)."""
        idx = self._read_index()
        items = [{"id": k, **v} for k, v in idx.items()]
        if tag:
            items = [i for i in items if tag in i.get("tags", [])]
        if os:
            items = [i for i in items if i.get("os") == os]
        items.sort(key=lambda i: i.get("last_used_at") or "", reverse=True)
        return items

    def load_all(self) -> Iterable[Profile]:
        for path in sorted(self.profiles_dir.glob("*.json")):
            if path.name.endswith(".tmp"):
                continue
            with path.open() as f:
                yield Profile.from_json(f.read())

    # --- maintenance ---

    def rebuild_index(self) -> int:
        """Rebuild index.json from the profiles dir. Returns count."""
        idx: Dict[str, Dict] = {}
        for p in self.load_all():
            idx[p.id] = self._index_entry(p)
        self._write_index(idx)
        return len(idx)

    def touch(self, profile_id: str) -> Profile:
        """Mark a profile as used. Returns the updated profile."""
        p = self.load(profile_id)
        p.touch()
        self.save(p)
        return p

    # --- rotation helpers ---

    def pick_least_recently_used(
        self, os: Optional[str] = None, tag: Optional[str] = None, exclude: Optional[List[str]] = None
    ) -> Optional[Dict]:
        """Return the LRU index entry matching filters, or None."""
        exclude = set(exclude or [])
        candidates = [i for i in self.list(os=os, tag=tag) if i["id"] not in exclude]
        if not candidates:
            return None
        # Profiles never used (last_used_at is None) come first.
        candidates.sort(key=lambda i: (i.get("last_used_at") or "", i.get("use_count", 0)))
        return candidates[0]

    def prune_older_than(self, cutoff_iso: str) -> int:
        """Delete profiles whose last_used_at < cutoff. Returns delete count.
        Profiles never used are NOT pruned."""
        count = 0
        for entry in self.list():
            last = entry.get("last_used_at")
            if last and last < cutoff_iso:
                self.delete(entry["id"])
                count += 1
        return count

    @staticmethod
    def utc_days_ago(days: int) -> str:
        from datetime import timedelta
        return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
