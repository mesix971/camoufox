"""
ScriptStore — on-disk persistence for recorded ActionScripts.

One JSON file per named script, plus an index.json for quick listing.
Same layout pattern and atomic-write semantics as proxypool.ProxyStore /
captchapool.ProviderStore.

Default location is ``~/.camoufox/macros/``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from actions.dsl import ActionScript


INDEX_FILENAME = "index.json"
SCRIPTS_DIRNAME = "scripts"

DEFAULT_ROOT = Path("~/.camoufox/macros").expanduser()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ScriptStore:
    """File-backed store for :class:`ActionScript` instances, keyed by name."""

    def __init__(self, root: Optional[str | Path] = None):
        self.root = Path(root).expanduser() if root is not None else DEFAULT_ROOT
        self.scripts_dir = self.root / SCRIPTS_DIRNAME
        self.index_path = self.root / INDEX_FILENAME
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
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

    def _index_entry(self, s: ActionScript) -> Dict:
        return {
            "name": s.name,
            "action_count": len(s.actions),
            "updated_at": _utc_now_iso(),
            "metadata": dict(s.metadata),
        }

    # --- CRUD ---

    def _script_path(self, name: str) -> Path:
        if not name or "/" in name or name.startswith("."):
            raise ValueError(f"invalid script name: {name!r}")
        return self.scripts_dir / f"{name}.json"

    def save(self, script: ActionScript) -> None:
        if not script.name:
            raise ValueError("script must have a name")
        path = self._script_path(script.name)
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w") as f:
            f.write(script.to_json())
        os.replace(tmp, path)
        idx = self._read_index()
        idx[script.name] = self._index_entry(script)
        self._write_index(idx)

    def load(self, name: str) -> ActionScript:
        path = self._script_path(name)
        if not path.exists():
            raise KeyError(f"script not found: {name}")
        with path.open() as f:
            return ActionScript.from_json(f.read())

    def exists(self, name: str) -> bool:
        return self._script_path(name).exists()

    def delete(self, name: str) -> None:
        path = self._script_path(name)
        if path.exists():
            path.unlink()
        idx = self._read_index()
        idx.pop(name, None)
        self._write_index(idx)

    def list(self) -> List[Dict]:
        idx = self._read_index()
        items = [{"name": k, **v} for k, v in idx.items()]
        items.sort(key=lambda i: i.get("name", ""))
        return items

    # --- maintenance ---

    def rebuild_index(self) -> int:
        """Rebuild the index from on-disk script files."""
        idx: Dict[str, Dict] = {}
        for path in sorted(self.scripts_dir.glob("*.json")):
            if path.name.endswith(".tmp"):
                continue
            try:
                with path.open() as f:
                    s = ActionScript.from_json(f.read())
            except Exception:
                continue
            idx[s.name] = self._index_entry(s)
        self._write_index(idx)
        return len(idx)
