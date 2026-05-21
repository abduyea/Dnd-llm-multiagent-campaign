"""
Ruleset-driven action-economy validation.

Per the M8 brief: each TTRPG ruleset specifies which combinations of
intents are legal in a single turn. The spine doesn't care which
ruleset is active — invariant 8 ("The core never branches on game
system") preserved. The single system-aware step in M8 is looking up
the ruleset's `ActionEconomyValidator` by name; the spine + dm + runner
stay generic.

dnd5e_lite ships the default validator:
  - ≤1 intent with cost "action"  (attack, examine)
  - ≤1 intent with cost "bonus"   (none in M8 vocabulary; rule exists for extension)
  - ≤1 intent with cost "move"
  - ≤MAX_INTENTS_PER_TURN total   (safety cap, not a TTRPG rule)
  - unlimited "free" intents      (look, talk)
  - "turn" cost (`wait`) must be the FINAL intent if present

This sibling-of-seed.py file is deliberately separate from seed.py's
`_RULESETS` (which is the attribute-schema validator used at load
time). Both are "ruleset-aware" but they fire at different points in
the lifecycle; consolidating them is a future refactor.
"""
from __future__ import annotations

from typing import Protocol

import config
from tags import IntentTag


class ActionEconomyValidator(Protocol):
    """Implementations decide which intent combinations are legal."""

    name: str

    def validate(self, intents: list[IntentTag]) -> tuple[bool, str | None]:
        """
        Return `(True, None)` if the turn plan is valid; else
        `(False, error_msg)` describing the specific violation. The
        error message feeds directly into the M3 retry correction so
        the player can adjust.
        """
        ...


class DND5eLiteEconomy:
    """
    M8 default. Three slot counts (action/bonus/move) plus unlimited
    free actions and a terminal-wait rule. The slot counts are 1 each
    in M8; future rulesets / classes / abilities may relax this.
    """

    name = "dnd5e_lite"

    def validate(self, intents: list[IntentTag]) -> tuple[bool, str | None]:
        if len(intents) > config.MAX_INTENTS_PER_TURN:
            return False, (
                f"too many intents in one turn: {len(intents)} "
                f"(max {config.MAX_INTENTS_PER_TURN})"
            )

        action_count = 0
        bonus_count = 0
        move_count = 0
        wait_seen = False

        for idx, intent in enumerate(intents):
            if wait_seen:
                # Anything appearing after a <wait/> is a structural error:
                # waiting consumes the rest of the turn.
                return False, (
                    "<intent type=\"wait\"/> must be the final intent in a turn; "
                    f"got more intents after position {idx - 1}"
                )

            cost = intent.cost
            if cost == "action":
                action_count += 1
                if action_count > 1:
                    return False, (
                        "too many actions: only 1 action-cost intent "
                        "(attack, examine) allowed per turn"
                    )
            elif cost == "bonus":
                bonus_count += 1
                if bonus_count > 1:
                    return False, "too many bonus actions: only 1 per turn"
            elif cost == "move":
                move_count += 1
                if move_count > 1:
                    return False, "too many moves: only 1 move per turn"
            elif cost == "turn":
                wait_seen = True
            elif cost == "free":
                pass  # unlimited (still bounded by MAX_INTENTS_PER_TURN)
            else:
                return False, f"unknown intent cost {cost!r}"

        return True, None


# ---------------------------------------------------------------------------
# Registry + lookup
# ---------------------------------------------------------------------------


_VALIDATORS: dict[str, ActionEconomyValidator] = {
    "dnd5e_lite": DND5eLiteEconomy(),
}


def get_action_economy(name: str) -> ActionEconomyValidator:
    """Look up the action-economy validator for a named ruleset.
    Raises `ValueError` if the ruleset is unknown — the seed loader
    has already validated `ruleset` at seed time, so a runtime miss
    here means a misconfigured caller, not a user error."""
    if name not in _VALIDATORS:
        raise ValueError(
            f"unknown ruleset {name!r} (known: {sorted(_VALIDATORS)})"
        )
    return _VALIDATORS[name]
