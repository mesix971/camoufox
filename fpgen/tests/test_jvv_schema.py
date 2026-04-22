"""End-to-end validation: generated config must pass Camoufox's own jvv schema.

This catches cases where properties.json types alone look right but the richer
jvv constraints (regex, range, group requirements) would reject the config.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
JSONVV_PATH = REPO_ROOT / "jsonvv"

# Add jsonvv to sys.path so it's importable without installation
sys.path.insert(0, str(JSONVV_PATH))

try:
    from jsonvv import JsonValidator  # type: ignore  # noqa: E402
except ImportError:
    pytest.skip("jsonvv not importable in this environment", allow_module_level=True)

from fpgen import generate, to_camoufox_config  # noqa: E402

SCHEMA_PATH = REPO_ROOT / "settings" / "camoucfg.jvv"


@pytest.fixture(scope="module")
def validator() -> JsonValidator:
    with SCHEMA_PATH.open() as f:
        schema = json.load(f)
    return JsonValidator(schema)


@pytest.mark.parametrize("seed", range(25))
def test_generated_config_passes_jvv(validator: JsonValidator, seed: int) -> None:
    p = generate(seed=seed)
    cfg = to_camoufox_config(p)
    validator.validate(cfg)  # raises on failure
