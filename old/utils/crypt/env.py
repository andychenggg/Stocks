"""Simple .env loader without external dependencies."""
from __future__ import annotations

import os


def load_env(path: str) -> None:
    if not path or not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"").strip("'")
            if not key:
                continue
            os.environ.setdefault(key, value)
