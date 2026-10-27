"""Append readable planning and dispatcher handoff details to a text file."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_OUTPUT_PATH = Path(__file__).resolve().parents[2] / "planning-output.txt"
_WRITE_LOCK = threading.Lock()
_LOGGER = logging.getLogger(__name__)


def write_planning_output(event: str, **details: Any) -> None:
    """Append one structured planning event to ``backend/planning-output.txt``."""
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = json.dumps(details, ensure_ascii=False, default=str, separators=(",", ":"))
    line = f"{timestamp} | {event} | {payload}\n"

    with _WRITE_LOCK:
        try:
            _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with _OUTPUT_PATH.open("a", encoding="utf-8", newline="") as output_file:
                output_file.write(line)
        except OSError:
            _LOGGER.exception("Could not append planning event to %s", _OUTPUT_PATH)

