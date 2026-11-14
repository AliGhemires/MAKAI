"""Configuration: `configs/makai.yaml` (shared, committed) overridden by
`configs/local.yaml` (per laptop, git-ignored: serial ports, robot IP...)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(os.environ.get("MAKAI_CONFIG_DIR", REPO_ROOT / "configs"))


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        out[key] = (
            _merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
        )
    return out


def load_config(config_dir: Path | None = None) -> dict[str, Any]:
    config_dir = config_dir or CONFIG_DIR
    cfg = yaml.safe_load((config_dir / "makai.yaml").read_text()) or {}
    local = config_dir / "local.yaml"
    if local.exists():
        cfg = _merge(cfg, yaml.safe_load(local.read_text()) or {})
    return cfg
