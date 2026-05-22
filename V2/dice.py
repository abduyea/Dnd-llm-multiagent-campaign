"""
Pure dice notation evaluator.

`roll(formula, rng) -> int` evaluates NdM+K notation against an injected
`random.Random`. The RNG is injected (not module-global) so that tests are
deterministic and the runner can seed it for replay reproducibility — the
M1 spine already guarantees replay reads `dice_rolled.result` rather than
re-rolling, but inside a single live run the runner owns the RNG.

Supported syntax:
  "1d20"      — one twenty-sided die
  "1d20+5"    — die roll plus modifier
  "2d6+3"     — multiple dice
  "1d8-1"     — negative modifier
  "5", "-3"   — pure constants (no dice)
Whitespace is tolerated. 'd' is case-insensitive.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field


_DICE_RE = re.compile(
    r"^\s*(\d+)\s*[dD]\s*(\d+)\s*(?:([+-])\s*(\d+))?\s*$",
)
_CONST_RE = re.compile(r"^\s*(-?\d+)\s*$")


class DiceFormulaError(ValueError):
    """Raised when a dice formula cannot be parsed."""


@dataclass(frozen=True)
class RollResult:
    """
    Decomposed roll outcome. `total == dice_total + mod`. `rolls` is the
    individual dice values (length 0 for pure constants).

    Mechanics uses this to build narration prompts that show the math
    (e.g. "1d8+3 = 6 + 3 = 9") without having to re-parse the formula.
    """

    formula: str
    total: int
    dice_total: int
    mod: int
    rolls: list[int] = field(default_factory=list)


def roll(formula: str, rng: random.Random) -> int:
    """Evaluate a dice formula against `rng`. Returns the integer total."""
    return roll_detailed(formula, rng).total


def roll_detailed(formula: str, rng: random.Random) -> RollResult:
    """Like `roll`, but returns the decomposition (dice sum, mod, individual rolls)."""
    if not isinstance(formula, str):
        raise DiceFormulaError(f"dice formula must be a string, got {type(formula).__name__}")

    const = _CONST_RE.match(formula)
    if const:
        value = int(const.group(1))
        return RollResult(formula=formula, total=value, dice_total=0, mod=value, rolls=[])

    m = _DICE_RE.match(formula)
    if not m:
        raise DiceFormulaError(f"unrecognized dice formula: {formula!r}")

    count = int(m.group(1))
    sides = int(m.group(2))
    if count < 1:
        raise DiceFormulaError(f"dice count must be >= 1: {formula!r}")
    if sides < 1:
        raise DiceFormulaError(f"dice sides must be >= 1: {formula!r}")

    sign = m.group(3)
    mod = int(m.group(4)) if sign else 0
    if sign == "-":
        mod = -mod

    rolls = [rng.randint(1, sides) for _ in range(count)]
    dice_total = sum(rolls)
    return RollResult(
        formula=formula,
        total=dice_total + mod,
        dice_total=dice_total,
        mod=mod,
        rolls=rolls,
    )
