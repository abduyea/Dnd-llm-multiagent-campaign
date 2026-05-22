"""
Debug log writer for exhausted-retry events.

Separate from `events.jsonl` by design — the event log is the game's
canonical record (M1 invariant 1), and developer-facing failure traces
do not belong there. The brief locates this file in the same run
directory so operators can find both side by side.

Append-only JSONL. One record per exhausted beat. Multiple records per
file when the same run sees multiple fallbacks.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_fallback_record(
    path: Path | str,
    *,
    turn_id: str,
    beat: str,
    player_id: str,
    location_id: str,
    player_text: str,
    model: str,
    attempts: list[dict[str, Any]],
) -> None:
    """
    Append one JSONL record describing an exhausted-retry beat.

    `attempts` is a list of dicts shaped:
        {"parse_status": str, "error_message": str | None, "raw_completion": str}

    The caller (typically the runner) builds these from its DM attempt
    objects. This module stays decoupled from dm.py's dataclasses so
    schema drift in either direction doesn't cross the boundary.
    """
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "turn_id": turn_id,
        "beat": beat,
        "player_id": player_id,
        "location_id": location_id,
        "player_text": player_text,
        "model": model,
        "attempts": attempts,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False))
        fh.write("\n")


def read_records(path: Path | str) -> list[dict[str, Any]]:
    """Read all records from a debug log. Returns empty list if the file
    does not exist (no fallbacks happened in this run)."""
    path = Path(path)
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
