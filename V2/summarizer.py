"""
Summarizer — Protocol + GlobalSummaryFilter + deferred per-player stub
+ the maybe_summarize wrapper that decides WHEN to fire.

The wrapper is the only thing that calls `provider.summarize`. Providers
own the content logic; the wrapper owns the trigger logic. This split
is the brief's locked design: changing trigger behavior touches one
place, changing summary style touches one place.

Per m6_build_brief.md:
  - Trigger: estimated player prompt > PROMPT_CHAR_BUDGET, on a PC turn.
  - Chain: each new summary chains the previous (covers_through advances).
  - Excluded from summary input: dice rolls, attribute deltas, infrastructure.
  - Excluded from trigger: NPC turns (their prompts don't grow with history).
"""
from __future__ import annotations

from typing import Callable, Protocol

import config
from eventlog import EventLog
from llm import DEFAULT_MODEL, ChatResult, chat as default_chat
from models import (
    AttributeSet,
    DMNarration,
    Event,
    EventCause,
    PlayerAction,
    SummaryCreated,
)
from projection import project
from view_builder import build_view, render_for_prompt


ChatFn = Callable[..., ChatResult]


# Conservative overhead estimate for the player prompt template (system
# role description + locked suffix + "What do you do?"). Tuned once,
# adjustable here. The brief locks the formula but not this exact value.
_PLAYER_PROMPT_TEMPLATE_OVERHEAD = 500


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class SummaryProvider(Protocol):
    """Produce a SummaryCreated covering everything in log_events since
    `previous_summary` (or all events if previous_summary is None).

    Implementations decide HOW (LLM call, heuristic, hand-written).
    The wrapper handles WHEN."""

    model: str

    def summarize(
        self,
        log_events: list[Event],
        previous_summary: SummaryCreated | None,
    ) -> SummaryCreated: ...


# ---------------------------------------------------------------------------
# GlobalSummaryFilter — M6's single implementation
# ---------------------------------------------------------------------------


class GlobalSummaryFilter:
    """One global summary at a time (latest wins from the view's
    perspective). Builds a chained summary by feeding the previous
    summary text + new narrative events to an LLM."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        chat_fn: ChatFn | None = None,
    ) -> None:
        self.model = model
        self._chat: ChatFn = chat_fn if chat_fn is not None else default_chat

    def summarize(
        self,
        log_events: list[Event],
        previous_summary: SummaryCreated | None,
    ) -> SummaryCreated:
        cutoff = previous_summary.covers_through if previous_summary else -1
        new_events = [e for e in log_events if e.seq > cutoff]
        last_seq = log_events[-1].seq if log_events else -1

        narrative_lines = _render_narrative_lines(new_events)
        prev_text = previous_summary.text if previous_summary else "(none yet)"

        new_events_block = (
            "\n".join(narrative_lines)
            if narrative_lines
            else "  (no narrative events since the last summary)"
        )

        user = (
            f"Previous summary:\n{prev_text}\n\n"
            f"New events since then:\n{new_events_block}\n\n"
            f"Produce a new combined summary covering everything through "
            f"seq {last_seq}."
        )

        messages = [
            {"role": "system", "content": _SUMMARY_SYSTEM},
            {"role": "user", "content": user},
        ]
        chat_result = self._chat(messages, model=self.model)
        text = chat_result.text.strip() or "(no summary produced)"

        return SummaryCreated(
            scope="world",
            covers_through=last_seq,
            text=text,
        )


class PerPlayerSummaryFilter:
    """Deferred per-player summarization. M6 ships this as a stub so
    the interface seam exists; the implementation is a later milestone.
    Any caller that wires this up will hit the NotImplementedError
    immediately, which is the desired behavior — fail loud, not silent."""

    model = "stub"

    def summarize(
        self,
        log_events: list[Event],
        previous_summary: SummaryCreated | None,
    ) -> SummaryCreated:
        raise NotImplementedError(
            "Per-player summarization is deferred. See m6_build_brief.md."
        )


# ---------------------------------------------------------------------------
# Trigger wrapper
# ---------------------------------------------------------------------------


def maybe_summarize(
    log: EventLog,
    next_actor_id: str,
    pc_ids: set[str],
    provider: SummaryProvider,
    budget_chars: int | None = None,
) -> bool:
    """
    Estimate the next prompt's size. If over budget AND the next actor
    is a PC, call the provider and append the resulting SummaryCreated
    event to the log. Returns True iff a summary was appended.

    NPC turns are never summarized — their intent prompt is small
    (scene snapshot only) and does not grow with history.
    """
    cap = budget_chars if budget_chars is not None else config.PROMPT_CHAR_BUDGET

    if next_actor_id not in pc_ids:
        return False

    estimated = _estimate_player_prompt_chars(log, next_actor_id)
    if estimated < cap:
        return False

    previous = _latest_summary(log.events())
    new_summary = provider.summarize(log.events(), previous)

    # Truncate to MAX_SUMMARY_CHARS so a single summary cannot itself
    # bloat the prompt past the next budget check.
    if len(new_summary.text) > config.MAX_SUMMARY_CHARS:
        truncated = new_summary.text[: config.MAX_SUMMARY_CHARS - 1].rstrip() + "…"
        new_summary = SummaryCreated(
            scope=new_summary.scope,
            covers_through=new_summary.covers_through,
            text=truncated,
        )

    log.append(new_summary, EventCause(kind="summarizer"))
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _estimate_player_prompt_chars(log: EventLog, player_id: str) -> int:
    """Char-count estimate of the player's next prompt. char_count / 4 ≈
    token count, conservative on real tokenizers."""
    events = log.events()
    state = project(events)
    view = build_view(events, player_id)
    rendered = render_for_prompt(view, state)
    return len(rendered) + _PLAYER_PROMPT_TEMPLATE_OVERHEAD


def _latest_summary(events: list[Event]) -> SummaryCreated | None:
    """The most recent SummaryCreated payload, or None if none exist."""
    latest: SummaryCreated | None = None
    for e in events:
        if isinstance(e.payload, SummaryCreated):
            latest = e.payload
    return latest


def _render_narrative_lines(events: list[Event]) -> list[str]:
    """Pick the narrative-relevant payloads and format them as bullet
    lines for the summarizer's user prompt. Mechanical bookkeeping
    (dice, deltas, entity_moved, etc.) is excluded by design."""
    lines: list[str] = []
    for event in events:
        p = event.payload
        if isinstance(p, PlayerAction):
            lines.append(f'  - {p.player_id}: "{p.text}"')
        elif isinstance(p, DMNarration):
            lines.append(f"  - DM: {p.text}")
        elif isinstance(p, AttributeSet) and p.attr == "status" and p.value == "dead":
            lines.append(f"  - {p.entity_id} died.")
    return lines


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------


_SUMMARY_SYSTEM = (
    "You are summarizing a tabletop RPG session for the players' future "
    "reference. Produce a concise summary (1-2 short paragraphs) of what "
    "has happened. Focus on persistent facts: who is in the party, who is "
    "alive or dead, what locations have been visited, what major "
    "encounters resolved. Skip incidental dialog and dice details. Do "
    "not invent events. Reply with the summary text only — no tags, no "
    "preamble."
)
