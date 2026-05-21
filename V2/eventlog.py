"""
Append-only event log. The single source of truth (invariant 1).

This module is pure storage and ordering. It does not project, validate
domain rules, or interpret events. It only:
  - assigns the next monotonic `seq` on append
  - holds events in `seq` order
  - persists to / reloads from disk (JSONL)

Persistence format is JSONL — one Event JSON per line — chosen because the
log is append-only by definition: a new event is one line appended to a file.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Iterator

from pydantic import TypeAdapter

from models import Event, EventCause, Payload

_PAYLOAD_ADAPTER: TypeAdapter[Payload] = TypeAdapter(Payload)


class EventLog:
    """
    Single-threaded, in-memory event log with optional file persistence.

    No concurrency (invariant 4). One event at a time.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self._events: list[Event] = []
        self._path: Path | None = Path(path) if path is not None else None
        # If a path is given and the file already exists, refuse to silently
        # overwrite. The caller must use EventLog.load(...) to resume.
        if self._path is not None and self._path.exists():
            raise FileExistsError(
                f"{self._path} exists; use EventLog.load() to resume or remove the file"
            )

    # ---- mutation -------------------------------------------------------

    def append(
        self,
        payload: Payload,
        cause: EventCause,
        timestamp: float | None = None,
    ) -> Event:
        """
        Append a new event. Assigns `seq` (next monotonic int).

        Timestamp defaults to wall clock but is informational only — never used
        for ordering (invariant 4).
        """
        seq = len(self._events)
        event = Event(
            seq=seq,
            timestamp=time.time() if timestamp is None else timestamp,
            cause=cause,
            payload=payload,
        )
        self._events.append(event)
        if self._path is not None:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(event.model_dump_json())
                fh.write("\n")
        return event

    # ---- read -----------------------------------------------------------

    def __iter__(self) -> Iterator[Event]:
        return iter(self._events)

    def __len__(self) -> int:
        return len(self._events)

    def __getitem__(self, idx: int) -> Event:
        return self._events[idx]

    def events(self) -> list[Event]:
        """Snapshot of the log as a fresh list, in seq order."""
        return list(self._events)

    # ---- persistence ----------------------------------------------------

    @classmethod
    def load(cls, path: Path | str) -> "EventLog":
        """Replay events from a JSONL file. The log they describe is rebuilt
        exactly: same seq, same payloads, same causes."""
        path = Path(path)
        log = cls.__new__(cls)  # bypass __init__ to skip the exists-check
        log._events = []
        log._path = path
        if not path.exists():
            return log
        with path.open("r", encoding="utf-8") as fh:
            for line_no, raw in enumerate(fh):
                raw = raw.strip()
                if not raw:
                    continue
                event = Event.model_validate_json(raw)
                if event.seq != len(log._events):
                    raise ValueError(
                        f"{path}:{line_no + 1}: seq {event.seq} out of order; "
                        f"expected {len(log._events)}"
                    )
                log._events.append(event)
        return log
