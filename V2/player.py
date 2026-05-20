"""
Player agent — emits a structured turn plan + prose narration.

M8 architectural shift: the PlayerAgent is now responsible for declaring
what its character does this turn as **structured intent tags**, plus a
freeform `<narration>` describing the character's prose. The DM no
longer interprets player prose into intent — the player has already
said.

Per M8 brief:
  - One or more `<intent>` tags (zero is valid = pass)
  - Exactly one `<narration>` tag
  - Ruleset (e.g. `dnd5e_lite`) validates the turn's action economy
  - Failures (malformed intent, ruleset violation, missing narration)
    trigger an M3-style retry with a chat-history correction
  - Narration prose: empty → `config.PLAYER_FALLBACK_TEXT`, long → truncated

The runner consumes `PlayerTurnResult.intents` (the validated plan) and
dispatches per intent (move stages EntityMoved, examine emits lore for
the DM narration, etc.). The runner ALSO appends the narration prose as
a `PlayerAction` event (unchanged from M4 — the player's record of
speech survives even if the rest of the turn falls back).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

import config
from llm import DEFAULT_MODEL, ChatResult, chat as default_chat
from models import WorldState
from ruleset import get_action_economy
from tags import (
    IntentTag,
    MalformedTagError,
    extract_intents,
    extract_narration,
)
from view_builder import PlayerView, render_for_prompt


_OPEN_NARRATION_RE = re.compile(r"<narration\b[^>]*>", re.DOTALL)
_CLOSE_NARRATION_RE = re.compile(r"</narration\s*>", re.DOTALL)


ChatFn = Callable[..., ChatResult]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlayerAttempt:
    """One LLM call's output. `parse_status` categorizes the outcome for
    retry / measurement; `intents` and `raw_narration` are populated on
    success and possibly on partial-success cases.

    Statuses:
      - "ok"                 : intents + narration both parsed cleanly
      - "salvaged_narration" : intents parsed cleanly; narration was
                               missing or truncated, prose was recovered
                               (open tag → end-of-output) or substituted
                               with PLAYER_FALLBACK_TEXT. Counts as
                               success for the retry loop; tracked
                               separately so we can monitor the rate of
                               LLM close-tag truncation.
      - "malformed_intent"   : intent tag failed to parse — retry
      - "no_narration"       : narration missing AND no intents present
                               (nothing salvageable) — retry
      - "economy_invalid"    : intents parsed but violated action economy
                               — retry
    """

    chat: ChatResult
    intents: list[IntentTag]
    raw_narration: str
    parse_status: str
    error_message: str | None


# Statuses that the retry loop treats as success (no further LLM calls
# needed). "salvaged_narration" is success-equivalent: the intents are
# valid and the prose is either the LLM's actual output minus a close
# tag, or a fallback string.
_SUCCESS_STATUSES = frozenset({"ok", "salvaged_narration"})


@dataclass(frozen=True)
class PlayerTurnResult:
    """Final result a runner consumes. `intents` is the validated plan
    (empty list when retries exhausted). `narration_text` is the final
    prose after strip/fallback/truncate processing."""

    chat: ChatResult
    intents: list[IntentTag]
    narration_text: str
    raw_text: str
    parse_status: str
    error_message: str | None
    attempts: list[PlayerAttempt] = field(default_factory=list)
    used_fallback: bool = False
    truncated: bool = False

    @property
    def succeeded(self) -> bool:
        return self.parse_status in _SUCCESS_STATUSES


# ---------------------------------------------------------------------------
# PlayerAgent
# ---------------------------------------------------------------------------


class PlayerAgent:
    def __init__(
        self,
        player_id: str,
        role_description: str,
        ruleset_name: str = "dnd5e_lite",
        model: str = DEFAULT_MODEL,
        chat_fn: ChatFn | None = None,
        retry_cap: int | None = None,
        goals: list[str] | None = None,
    ) -> None:
        self.player_id = player_id
        self.role_description = role_description
        self.ruleset_name = ruleset_name
        self.model = model
        self._chat: ChatFn = chat_fn if chat_fn is not None else default_chat
        self.retry_cap = retry_cap if retry_cap is not None else config.RETRY_CAP
        self.goals: list[str] = list(goals) if goals else []
        # Counter for the empty-intent-loop escalation. Increments when a
        # turn resolves "ok" with zero intents; resets when the agent
        # commits to at least one intent. Read at the top of `act()` to
        # decide whether to escalate the prompt.
        self._consecutive_empty_intent_turns: int = 0

    def act(self, view: PlayerView, state: WorldState) -> PlayerTurnResult:
        if view.player_id != self.player_id:
            raise ValueError(
                f"PlayerAgent for {self.player_id!r} given a view for "
                f"{view.player_id!r}"
            )

        messages = build_player_prompt(
            view, state, self.role_description, goals=self.goals,
            empty_intent_streak=self._consecutive_empty_intent_turns,
        )
        validator = get_action_economy(self.ruleset_name)
        attempts: list[PlayerAttempt] = []

        for attempt_idx in range(1 + self.retry_cap):
            chat_result = self._chat(messages, model=self.model)
            attempt = _classify_player_output(chat_result, validator)
            attempts.append(attempt)

            if attempt.parse_status in _SUCCESS_STATUSES:
                narration_text, used_fallback, truncated = _process_narration(
                    attempt.raw_narration
                )
                result = PlayerTurnResult(
                    chat=chat_result,
                    intents=attempt.intents,
                    narration_text=narration_text,
                    raw_text=chat_result.text,
                    parse_status=attempt.parse_status,
                    error_message=attempt.error_message,
                    attempts=attempts,
                    used_fallback=used_fallback,
                    truncated=truncated,
                )
                self._update_empty_intent_streak(result.intents)
                return result

            if attempt_idx == self.retry_cap:
                break

            messages = messages + [
                {"role": "assistant", "content": chat_result.raw},
                {"role": "user", "content": _correction_for(attempt)},
            ]

        # Exhausted retries — return the last attempt's data with intents
        # cleared (an invalid turn plan is not safe to execute).
        last = attempts[-1]
        narration_text, used_fallback, truncated = _process_narration(
            last.raw_narration or ""
        )
        result = PlayerTurnResult(
            chat=last.chat,
            intents=[],
            narration_text=narration_text,
            raw_text=last.chat.text,
            parse_status=last.parse_status,
            error_message=last.error_message,
            attempts=attempts,
            used_fallback=used_fallback,
            truncated=truncated,
        )
        # Exhausted-retries is mechanically equivalent to an empty-intent
        # turn (no intents dispatched). Count it toward the streak so the
        # escalation fires after persistent no-progress regardless of
        # whether the cause is "LLM passed" or "LLM produced garbage".
        self._update_empty_intent_streak(result.intents)
        return result

    def _update_empty_intent_streak(self, intents: list) -> None:
        if intents:
            self._consecutive_empty_intent_turns = 0
        else:
            self._consecutive_empty_intent_turns += 1


# ---------------------------------------------------------------------------
# Classification + correction
# ---------------------------------------------------------------------------


def _classify_player_output(chat_result: ChatResult, validator) -> PlayerAttempt:
    """Parse intents + narration from the LLM's text, validate against
    the action economy, return a categorized PlayerAttempt."""
    # 1. Intent tags (zero or more, in order).
    try:
        intents = extract_intents(chat_result.text)
    except MalformedTagError as e:
        return PlayerAttempt(
            chat=chat_result, intents=[], raw_narration="",
            parse_status="malformed_intent",
            error_message=str(e),
        )

    # 2. Narration tag (exactly one required, with soft-recover).
    salvage_note: str | None = None
    try:
        narration = extract_narration(chat_result.text)
        raw_narration = narration.text
    except MalformedTagError as e:
        # Soft-recover: if intents parsed clean, we want to use them
        # rather than retry-discard the entire turn. The LLM's most
        # common close-tag failure is `<narration>prose...` with no
        # `</narration>` — a truncation pattern. Try to salvage the
        # prose; failing that, fall back to PLAYER_FALLBACK_TEXT.
        if not intents:
            return PlayerAttempt(
                chat=chat_result, intents=intents, raw_narration="",
                parse_status="no_narration",
                error_message=str(e),
            )
        salvaged = _salvage_narration_prose(chat_result.text)
        if salvaged:
            raw_narration = salvaged
            salvage_note = (
                f"recovered prose from truncated/unclosed <narration> "
                f"tag ({len(salvaged)} chars); original error: {e}"
            )
        else:
            # No salvageable prose. Accept intents with empty narration;
            # _process_narration will substitute PLAYER_FALLBACK_TEXT.
            raw_narration = ""
            salvage_note = (
                f"no <narration> tag found in output; intents accepted "
                f"with fallback prose; original error: {e}"
            )

    # 3. Action economy.
    ok, err = validator.validate(intents)
    if not ok:
        return PlayerAttempt(
            chat=chat_result, intents=intents, raw_narration=raw_narration,
            parse_status="economy_invalid",
            error_message=err,
        )

    if salvage_note is not None:
        return PlayerAttempt(
            chat=chat_result, intents=intents, raw_narration=raw_narration,
            parse_status="salvaged_narration",
            error_message=salvage_note,
        )
    return PlayerAttempt(
        chat=chat_result, intents=intents, raw_narration=raw_narration,
        parse_status="ok",
        error_message=None,
    )


def _salvage_narration_prose(raw_text: str) -> str | None:
    """Recover narration prose from output where the close tag is
    missing or malformed.

    Returns the stripped prose text following an `<narration>` open tag,
    or None if no open tag is found. If a stray `</narration>` close
    tag appears later in the output, the prose is truncated at it.
    """
    m = _OPEN_NARRATION_RE.search(raw_text)
    if m is None:
        return None
    tail = raw_text[m.end():]
    close_match = _CLOSE_NARRATION_RE.search(tail)
    if close_match is not None:
        tail = tail[: close_match.start()]
    tail = tail.strip()
    return tail or None


def _process_narration(raw: str) -> tuple[str, bool, bool]:
    """Strip → fallback if empty → truncate if long.
    Returns (final_text, used_fallback, truncated)."""
    stripped = raw.strip()
    if not stripped:
        return config.PLAYER_FALLBACK_TEXT, True, False
    if len(stripped) > config.MAX_PLAYER_OUTPUT_CHARS:
        return (
            stripped[: config.MAX_PLAYER_OUTPUT_CHARS - 1].rstrip() + "…",
            False,
            True,
        )
    return stripped, False, False


def _correction_for(attempt: PlayerAttempt) -> str:
    """Build the M3-style retry correction message based on the failure
    category. Goes into the chat history as a user message."""
    if attempt.parse_status == "malformed_intent":
        return (
            "Your previous response had a malformed intent tag: "
            f"{attempt.error_message}. "
            "Reply with zero or more well-formed <intent type=\"...\" "
            "target=\"...\"/> tags (or <intent type=\"talk\" "
            "target=\"...\">speech</intent>) followed by exactly one "
            "<narration>your prose</narration> tag. Valid intent types: "
            "look, examine, move, attack, talk, wait, check, use_item, "
            "puzzle_answer, pickup, give, open, trade. Use only ids from "
            "your affordances list."
        )
    if attempt.parse_status == "no_narration":
        return (
            "Your previous response did not contain a "
            "<narration>...</narration> tag. Reply with your intent tags "
            "AND a single non-empty narration tag describing what your "
            "character does and says in 1-2 sentences."
        )
    if attempt.parse_status == "economy_invalid":
        return (
            "Your previous turn plan violated the action economy: "
            f"{attempt.error_message}. Revise your intent tags so the turn "
            "is legal — at most 1 action (attack OR examine OR check OR "
            "use_item OR puzzle_answer OR pickup OR give OR open OR "
            "trade), at most 1 move, unlimited free actions (look, talk). "
            "<wait/> must be the final intent if present."
        )
    return (
        f"Previous response was invalid ({attempt.parse_status}). "
        "Reply with valid intent tags + one <narration> tag."
    )


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------


_PLAYER_SYSTEM_SUFFIX = (
    " You are a player in a tabletop RPG. You only know what you have "
    "witnessed below. Reply with a planned turn: zero or more <intent> "
    "tags describing your character's actions, followed by exactly one "
    "<narration> tag with your character's prose (what they do and say "
    "in 1-2 sentences). Use only the ids in your affordances list — do "
    "not invent ids. Do not invent dice rolls or game mechanics; the "
    "Dungeon Master resolves all rolls.\n\n"
    "Forward progress: If your affordances list says there are no valid "
    "targets in this scene for the action you want (e.g. \"no DC-bearing "
    "targets here\", \"no puzzle targets here\", \"NO valid target in "
    "this scene\"), or if a previous turn's DM narration explicitly told "
    "you your action did nothing here, do NOT keep retrying the same "
    "action on the same target. Move to a connected room — the thing "
    "you need is probably somewhere else. Repeating a SKIPPED action "
    "wastes the party's turns and never starts working."
)


def build_player_prompt(
    view: PlayerView,
    state: WorldState,
    role_description: str,
    goals: list[str] | None = None,
    empty_intent_streak: int = 0,
) -> list[dict[str, str]]:
    system = role_description.strip() + _PLAYER_SYSTEM_SUFFIX
    if goals:
        bullets = "\n".join(f"  - {g}" for g in goals)
        system += (
            "\n\n[Your party's objective]\n"
            f"{bullets}\n"
            "Keep these objectives in mind on every turn. If the current "
            "scene offers no obvious progress toward them, the next step "
            "is almost always to MOVE to a connected room — the dungeon "
            "is larger than what you can see from where you stand, and "
            "the items / NPCs / challenges that advance the objective "
            "are somewhere you have not yet been."
        )
    if empty_intent_streak >= config.EMPTY_INTENT_ESCALATION_THRESHOLD:
        system += (
            "\n\n[Forward-progress override]\n"
            f"You have passed {empty_intent_streak} turn(s) in a row "
            "without committing to any <intent> tag. This turn you MUST "
            "declare at least one <intent>. Pick the most promising "
            "option from your affordances list — a <intent type=\"move\" "
            "target=\"<connected_id>\"/> to a connected room is almost "
            "always valid and is the right answer when the current scene "
            "feels stuck. Pure narration this turn will not advance the "
            "party."
        )
    if view.consecutive_turns_here >= config.ROOM_STICKINESS_ESCALATION_THRESHOLD:
        system += (
            "\n\n[Room-stickiness pressure]\n"
            f"You have spent {view.consecutive_turns_here} consecutive "
            "turns in this room without moving. Repeated <talk> or "
            "<examine> intents on the same targets are valid but they "
            "are not advancing your party's objectives — those "
            "objectives reference places you have not yet been. If the "
            "current scene has not yielded a new mechanical state (a "
            "successful check, a freed NPC, a picked lock, a recovered "
            "item) in the next turn, the right move is "
            "<intent type=\"move\" target=\"<connected_id>\"/> to a "
            "connected room. The thing you need to advance is almost "
            "certainly somewhere else."
        )
    rendered = render_for_prompt(view, state)
    user = rendered + "\n\nWhat does your character do this turn?"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
