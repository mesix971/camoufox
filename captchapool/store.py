"""
Provider credential store.

One JSON file per provider entry, stored in a directory. Same layout
pattern as fpgen.ProfileStore / proxypool.ProxyStore.

Layout:
    <root>/
        providers/
            <name>.json          # {"name", "provider_type", "api_key", "priority", ...}
        index.json               # name -> {provider_type, priority, created_at}

SECURITY NOTE
-------------
API keys are stored as PLAINTEXT JSON on local disk. This is a deliberate
simplification: any encryption-at-rest scheme still needs a key to decrypt,
and on a single-user workstation that key would live next to the ciphertext
anyway (a local keyring or a passphrase file the user autoloads). If an
attacker has read access to ~/.camoufox/captchapool/, they already own the
machine and everything else the user has authenticated against. Don't put
these files on shared/multi-tenant hosts; on those use the providers' own
IP whitelisting features instead.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from captchapool.providers.base import CaptchaProvider
from captchapool.providers.capsolver import CapSolverProvider
from captchapool.providers.twocaptcha import TwoCaptchaProvider
from captchapool.solver import Solver


INDEX_FILENAME = "index.json"
PROVIDERS_DIRNAME = "providers"

_PROVIDER_TYPES = ("capsolver", "twocaptcha")
_PROVIDER_CLASSES: Dict[str, type] = {
    "capsolver": CapSolverProvider,
    "twocaptcha": TwoCaptchaProvider,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _redact(api_key: str) -> str:
    """Redact an API key for display. Keeps first 4 / last 2 chars."""
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}{'*' * (len(api_key) - 6)}{api_key[-2:]}"


class ProviderStore:
    """On-disk store for captcha provider credentials.

    Writes one JSON file per named provider under
    ``<root>/providers/<name>.json`` plus a lightweight ``index.json``
    cache that can be rebuilt at any time.

    .. warning::
       API keys are stored in plaintext. See module docstring.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser()
        self.providers_dir = self.root / PROVIDERS_DIRNAME
        self.index_path = self.root / INDEX_FILENAME
        self.providers_dir.mkdir(parents=True, exist_ok=True)
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

    def _index_entry(self, entry: Dict) -> Dict:
        return {
            "provider_type": entry["provider_type"],
            "priority": entry.get("priority", 0),
            "created_at": entry.get("created_at"),
        }

    # --- CRUD ---

    def _provider_path(self, name: str) -> Path:
        if not name or "/" in name or name.startswith("."):
            raise ValueError(f"invalid provider name: {name!r}")
        return self.providers_dir / f"{name}.json"

    def save(
        self,
        name: str,
        api_key: str,
        provider_type: str,
        priority: int = 0,
    ) -> Dict:
        """Save/overwrite a provider entry.

        Args:
            name: user-chosen label (must be filesystem-safe).
            api_key: provider API key (stored plaintext — see module docs).
            provider_type: one of "capsolver" or "twocaptcha".
            priority: lower numbers are tried first by `build_solver()`.

        Returns the saved entry dict.
        """
        if provider_type not in _PROVIDER_TYPES:
            raise ValueError(
                f"unknown provider_type {provider_type!r}; must be one of {_PROVIDER_TYPES}"
            )
        if not api_key:
            raise ValueError("api_key must be non-empty")

        entry = {
            "name": name,
            "provider_type": provider_type,
            "api_key": api_key,
            "priority": priority,
            "created_at": _utc_now_iso(),
        }
        path = self._provider_path(name)
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w") as f:
            json.dump(entry, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
        idx = self._read_index()
        idx[name] = self._index_entry(entry)
        self._write_index(idx)
        return entry

    def load(self, name: str) -> Dict:
        """Return the full entry (INCLUDING api_key) for the named provider."""
        path = self._provider_path(name)
        if not path.exists():
            raise KeyError(f"provider not found: {name}")
        with path.open() as f:
            return json.load(f)

    def exists(self, name: str) -> bool:
        return self._provider_path(name).exists()

    def delete(self, name: str) -> None:
        path = self._provider_path(name)
        if path.exists():
            path.unlink()
        idx = self._read_index()
        idx.pop(name, None)
        self._write_index(idx)

    def list(self, provider_type: Optional[str] = None) -> List[Dict]:
        """Return all entries, WITH api_key redacted, sorted by priority then name."""
        idx = self._read_index()
        items: List[Dict] = []
        for name, meta in idx.items():
            if provider_type and meta.get("provider_type") != provider_type:
                continue
            try:
                full = self.load(name)
            except KeyError:
                continue
            items.append(
                {
                    "name": name,
                    "provider_type": full.get("provider_type"),
                    "priority": full.get("priority", 0),
                    "created_at": full.get("created_at"),
                    "api_key": _redact(full.get("api_key", "")),
                }
            )
        items.sort(key=lambda i: (i.get("priority", 0), i["name"]))
        return items

    # --- maintenance ---

    def rebuild_index(self) -> int:
        """Rebuild index.json from disk. Returns number of entries."""
        idx: Dict[str, Dict] = {}
        for path in sorted(self.providers_dir.glob("*.json")):
            if path.name.endswith(".tmp"):
                continue
            with path.open() as f:
                entry = json.load(f)
            idx[entry["name"]] = self._index_entry(entry)
        self._write_index(idx)
        return len(idx)

    # --- solver construction ---

    def _instantiate(self, entry: Dict) -> CaptchaProvider:
        cls = _PROVIDER_CLASSES[entry["provider_type"]]
        return cls(api_key=entry["api_key"])

    def build_solver(self, strategy: str = "first") -> Solver:
        """Instantiate every stored provider, sorted by priority, and wrap
        them in a Solver. Lower priority numbers come first."""
        entries: List[Dict] = []
        for name in self._read_index():
            try:
                entries.append(self.load(name))
            except KeyError:
                continue
        entries.sort(key=lambda e: (e.get("priority", 0), e["name"]))
        if not entries:
            raise ValueError("no providers stored; add some with save() first")
        providers = [self._instantiate(e) for e in entries]
        return Solver(providers, strategy=strategy)
