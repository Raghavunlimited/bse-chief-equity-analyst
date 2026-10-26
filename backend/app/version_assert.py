"""Shared APP_VERSION floor checks for tests (not imported by production routers)."""
from __future__ import annotations

import re


def minor_at_least(version: str, min_minor: int) -> bool:
    """True when version matches ``5.<minor>.*`` and minor >= min_minor."""
    m = re.match(r"^5\.(\d+)\.", version or "")
    return bool(m and int(m.group(1)) >= min_minor)
