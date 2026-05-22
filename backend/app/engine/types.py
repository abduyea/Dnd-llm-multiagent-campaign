from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Statuses that indicate a character is out of play — single source of truth for all engine checks.
NEUTRALIZED_STATUSES: frozenset[str] = frozenset(
    {"dead", "fled", "knocked_out", "surrender", "unconscious", "dying"}
)


@dataclass(frozen=True)
class ActionEconomy:
    action: bool = True
    bonus_action: bool = True
    reaction: bool = True
    movement_remaining: int = 30

    def is_empty(self) -> bool:
        """Return True when all action types (action, bonus, reaction) are spent."""
        return not self.action and not self.bonus_action and not self.reaction


@dataclass(frozen=True)
class CharacterState:
    id: str
    name: str
    hp_current: int
    hp_max: int
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int
    armor_class: int
    initiative_bonus: int
    speed: int
    conditions: tuple[str, ...] = ()
    action_economy: ActionEconomy = field(default_factory=ActionEconomy)

    @property
    def is_alive(self) -> bool:
        """Return True if hp_current > 0."""
        return self.hp_current > 0

    @property
    def is_conscious(self) -> bool:
        """Return True if alive and not carrying an unconscious or dead condition."""
        return (
            self.is_alive and "unconscious" not in self.conditions and "dead" not in self.conditions
        )


@dataclass(frozen=True)
class InitiativeEntry:
    character_id: str
    initiative: int
    order: int


@dataclass(frozen=True)
class GameState:
    session_id: str
    campaign_id: str
    turn_number: int
    current_character_id: str | None
    initiative_order: tuple[InitiativeEntry, ...] = ()
    characters: dict[str, CharacterState] = field(default_factory=dict)
    scene_id: str | None = None

    def character_by_id(self, character_id: str) -> CharacterState | None:
        """Look up a character by id; returns None if not present."""
        return self.characters.get(character_id)

    def alive_characters(self) -> list[CharacterState]:
        """Return all characters with hp_current > 0."""
        return [c for c in self.characters.values() if c.is_alive]

    def conscious_characters(self) -> list[CharacterState]:
        """Return all characters that are alive and not unconscious/dead."""
        return [c for c in self.characters.values() if c.is_conscious]


@dataclass(frozen=True)
class DiceRoll:
    num_dice: int
    sides: int
    modifier: int = 0

    def expression(self) -> str:
        """Reconstruct the canonical dice expression string (e.g. '2d6+3')."""
        base = f"{self.num_dice}d{self.sides}"
        if self.modifier >= 0:
            return f"{base}+{self.modifier}"
        return f"{base}{self.modifier}"


@dataclass(frozen=True)
class DiceResult:
    rolls: tuple[int, ...]
    modifier: int = 0
    total: int = 0
    expression: str = ""

    def __post_init__(self) -> None:
        if self.total == 0 and self.rolls:
            object.__setattr__(self, "total", sum(self.rolls) + self.modifier)


@dataclass(frozen=True)
class AttackResult:
    attacker_id: str
    target_id: str
    attack_roll: int
    natural_roll: int
    is_critical: bool
    is_hit: bool
    damage: int
    damage_rolls: tuple[int, ...]
    damage_type: str = "slashing"


@dataclass(frozen=True)
class ActionInput:
    session_id: str
    character_id: str
    action_type: str
    target_id: str | None = None
    dice_expression: str | None = None
    description: str = ""
    seed: int | None = None
    enemies: tuple[dict[str, Any], ...] = ()
    location: str | None = None  # current location label from frontend tracker


@dataclass(frozen=True)
class TurnDelta:
    turn_number: int
    character_id: str
    action_type: str
    action_description: str
    dice_results: list[DiceResult]
    attack_results: list[AttackResult]
    state_changes: dict[str, CharacterState]
    initiative_order: tuple[InitiativeEntry, ...]
    narration: str = ""
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class CheckResolution:
    """Structured outcome of a D&D 5e ability check."""

    stat: str
    stat_mod: int
    dc: int
    d20: int
    total: int
    success: bool


@dataclass(frozen=True)
class Violation:
    field: str
    message: str
    code: str
