"""
Proxy persistence.

Same layout pattern as fpgen.ProfileStore: one JSON per proxy + an index.
Chosen over SQLite so individual proxies can be hand-edited or checked into
version control.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from proxypool.proxy import Proxy, ProxyStatus


INDEX_FILENAME = "index.json"
PROXIES_DIRNAME = "proxies"


class ProxyStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser()
        self.proxies_dir = self.root / PROXIES_DIRNAME
        self.index_path = self.root / INDEX_FILENAME
        self.proxies_dir.mkdir(parents=True, exist_ok=True)
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

    def _index_entry(self, p: Proxy) -> Dict:
        return {
            "label": p.label,
            "provider": p.provider,
            "scheme": p.scheme,
            "host": p.host,
            "port": p.port,
            "status": p.status,
            "country": p.country,
            "observed_country": p.observed_country,
            "latency_ms": p.latency_ms,
            "tags": list(p.tags),
            "last_used_at": p.last_used_at,
            "last_checked_at": p.last_checked_at,
            "use_count": p.use_count,
        }

    # --- CRUD ---

    def _proxy_path(self, proxy_id: str) -> Path:
        return self.proxies_dir / f"{proxy_id}.json"

    def save(self, p: Proxy) -> None:
        path = self._proxy_path(p.id)
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w") as f:
            f.write(p.to_json())
        os.replace(tmp, path)
        idx = self._read_index()
        idx[p.id] = self._index_entry(p)
        self._write_index(idx)

    def save_many(self, proxies: Iterable[Proxy]) -> int:
        count = 0
        idx = self._read_index()
        for p in proxies:
            path = self._proxy_path(p.id)
            tmp = path.with_suffix(".json.tmp")
            with tmp.open("w") as f:
                f.write(p.to_json())
            os.replace(tmp, path)
            idx[p.id] = self._index_entry(p)
            count += 1
        self._write_index(idx)
        return count

    def load(self, proxy_id: str) -> Proxy:
        path = self._proxy_path(proxy_id)
        if not path.exists():
            raise KeyError(f"proxy not found: {proxy_id}")
        with path.open() as f:
            return Proxy.from_json(f.read())

    def exists(self, proxy_id: str) -> bool:
        return self._proxy_path(proxy_id).exists()

    def delete(self, proxy_id: str) -> None:
        path = self._proxy_path(proxy_id)
        if path.exists():
            path.unlink()
        idx = self._read_index()
        idx.pop(proxy_id, None)
        self._write_index(idx)

    def list(
        self,
        status: Optional[str] = None,
        provider: Optional[str] = None,
        tag: Optional[str] = None,
        country: Optional[str] = None,
    ) -> List[Dict]:
        idx = self._read_index()
        items = [{"id": k, **v} for k, v in idx.items()]
        if status:
            items = [i for i in items if i.get("status") == status]
        if provider:
            items = [i for i in items if i.get("provider") == provider]
        if tag:
            items = [i for i in items if tag in i.get("tags", [])]
        if country:
            items = [i for i in items
                     if (i.get("country") or "").upper() == country.upper()
                     or (i.get("observed_country") or "").upper() == country.upper()]
        items.sort(key=lambda i: (i.get("status", ""), i.get("label", "")))
        return items

    def load_all(
        self,
        status: Optional[str] = None,
        provider: Optional[str] = None,
        tag: Optional[str] = None,
        country: Optional[str] = None,
    ) -> Iterable[Proxy]:
        for entry in self.list(status=status, provider=provider, tag=tag, country=country):
            yield self.load(entry["id"])

    # --- maintenance ---

    def rebuild_index(self) -> int:
        idx: Dict[str, Dict] = {}
        for path in sorted(self.proxies_dir.glob("*.json")):
            if path.name.endswith(".tmp"):
                continue
            with path.open() as f:
                p = Proxy.from_json(f.read())
            idx[p.id] = self._index_entry(p)
        self._write_index(idx)
        return len(idx)

    def prune(self, status: str = ProxyStatus.DEAD.value) -> int:
        """Delete all proxies matching the given status. Returns count deleted."""
        entries = self.list(status=status)
        for e in entries:
            self.delete(e["id"])
        return len(entries)

    def touch(self, proxy_id: str) -> Proxy:
        p = self.load(proxy_id)
        p.touch()
        self.save(p)
        return p

    def find_by_host_port(self, host: str, port: int) -> Optional[Proxy]:
        """Dedup helper — find an existing proxy by host+port (ignoring auth)."""
        for entry in self.list():
            if entry.get("host") == host and entry.get("port") == port:
                return self.load(entry["id"])
        return None

    def find_by_signature(
        self, host: str, port: int, username: Optional[str], password: Optional[str]
    ) -> Optional[Proxy]:
        """Stricter dedup — match on full auth tuple.

        Needed for rotating providers like iproyal where the same host:port is
        reused with different session IDs embedded in the username; those are
        genuinely different proxy sessions and must not be treated as dupes.
        """
        for entry in self.list():
            if entry.get("host") != host or entry.get("port") != port:
                continue
            p = self.load(entry["id"])
            if p.username == username and p.password == password:
                return p
        return None
