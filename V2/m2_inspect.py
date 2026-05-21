"""
Run inspection + batch summary, M3-aware.

What this module auto-checks per run:
  1. Event sequence matches either the documented hit/miss/downed shape
     OR the M3 fallback shape (PlayerAction + neutral DMNarration).
  2. Internal arithmetic on full turns (attack d20 in range,
     attribute_delta.delta == -damage_total, post-replay hp consistent).
  3. Replay-correctness (M1 invariant 12) on every log shape.

Fallback turns pass auto-check; they show up in the summary as
`fell_back` instead of `succeeded` so the operator can see the
proportion of turns that exhausted retries.

The narration-consistency check stays hand-only (semantic alignment
between prose and rolled outcome).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any

import config
from eventlog import EventLog
from llm import ChatResult
from models import (
    AttributeDelta,
    AttributeSet,
    DMNarration,
    DiceRolled,
    PlayerAction,
)
from projection import project


# ---------------------------------------------------------------------------
# Measurement sink — implements runner.MeasurementSink Protocol
# ---------------------------------------------------------------------------


class MeasurementSink:
    """One record per LLM call (including retries). `attempt_idx` is the
    0-based call index within a beat (0=initial, 1+=retries)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.records: list[dict[str, Any]] = []

    def record(
        self,
        beat: str,
        chat: ChatResult,
        parse_status: str,
        error_message: str | None,
        attempt_idx: int,
    ) -> None:
        self.records.append(
            {
                "beat": beat,
                "attempt_idx": attempt_idx,
                "model": chat.model,
                "prompt_chars": chat.prompt_chars,
                "completion_chars": chat.completion_chars,
                "latency_s": chat.latency_s,
                "parse_status": parse_status,
                "error_message": error_message,
                "raw_completion": chat.raw,
            }
        )

    def dump(self) -> None:
        self.path.write_text(json.dumps(self.records, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Per-run inspection
# ---------------------------------------------------------------------------


_FALLBACK_TEXTS: frozenset[str] = frozenset(
    {config.FALLBACK_INTENT_TEXT, config.FALLBACK_NARRATION_TEXT}
)


@dataclass
class TurnInspection:
    run_dir: Path
    sequence_ok: bool
    arithmetic_ok: bool
    replay_ok: bool
    hit: bool | None
    downed: bool | None
    fell_back: bool
    fallback_beat: str | None  # "intent" | "narration" | None
    failure_reason: str | None
    notes: list[str] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return self.sequence_ok and self.arithmetic_ok and self.replay_ok

    @property
    def succeeded(self) -> bool:
        return self.all_ok and not self.fell_back


def inspect_run(run_dir: Path) -> TurnInspection:
    """Auto-check a single run directory (M2 normal or M3 fallback shape)."""
    run_dir = Path(run_dir)
    log = EventLog.load(run_dir / "events.jsonl")
    events = log.events()

    turn_start = _find_turn_start(events)
    if turn_start is None:
        return TurnInspection(
            run_dir=run_dir,
            sequence_ok=False, arithmetic_ok=False, replay_ok=False,
            hit=None, downed=None,
            fell_back=False, fallback_beat=None,
            failure_reason="no PlayerAction in log — turn never started",
        )

    pre_state = project(events[:turn_start])
    turn_events = events[turn_start:]

    fallback_beat = _detect_fallback(turn_events)
    if fallback_beat is not None:
        replay_ok, replay_reason = _check_replay(events)
        return TurnInspection(
            run_dir=run_dir,
            sequence_ok=True,
            arithmetic_ok=True,  # nothing to compute; vacuously ok
            replay_ok=replay_ok,
            hit=None, downed=None,
            fell_back=True, fallback_beat=fallback_beat,
            failure_reason=None if replay_ok else f"replay: {replay_reason}",
            notes=[f"fallback ({fallback_beat}): no mechanics committed"],
        )

    seq_ok, seq_reason, hit, downed = _check_sequence(turn_events)
    if not seq_ok:
        return TurnInspection(
            run_dir=run_dir,
            sequence_ok=False, arithmetic_ok=False, replay_ok=False,
            hit=hit, downed=downed,
            fell_back=False, fallback_beat=None,
            failure_reason=f"sequence: {seq_reason}",
        )

    post_state = project(events)
    arith_ok, arith_reason, notes = _check_arithmetic(turn_events, pre_state, post_state, hit)
    replay_ok, replay_reason = _check_replay(events)

    failure_reason = None
    if not arith_ok:
        failure_reason = f"arithmetic: {arith_reason}"
    elif not replay_ok:
        failure_reason = f"replay: {replay_reason}"

    return TurnInspection(
        run_dir=run_dir,
        sequence_ok=True,
        arithmetic_ok=arith_ok,
        replay_ok=replay_ok,
        hit=hit, downed=downed,
        fell_back=False, fallback_beat=None,
        failure_reason=failure_reason,
        notes=notes,
    )


def _find_turn_start(events) -> int | None:
    for i, e in enumerate(events):
        if isinstance(e.payload, PlayerAction):
            return i
    return None


def _detect_fallback(turn_events) -> str | None:
    """If turn_events is [PlayerAction, DMNarration(fallback_text)], return
    which beat fell back. Otherwise None.

    M3 fallback shape: exactly two events, the second being a DMNarration
    whose text is one of the configured fallback strings."""
    if len(turn_events) != 2:
        return None
    if not isinstance(turn_events[0].payload, PlayerAction):
        return None
    if not isinstance(turn_events[1].payload, DMNarration):
        return None
    text = turn_events[1].payload.text
    if text == config.FALLBACK_INTENT_TEXT:
        return "intent"
    if text == config.FALLBACK_NARRATION_TEXT:
        return "narration"
    return None


def _check_sequence(turn_events) -> tuple[bool, str | None, bool | None, bool | None]:
    if len(turn_events) < 3:
        return False, f"too few turn events ({len(turn_events)})", None, None

    payloads = [e.payload for e in turn_events]

    if not isinstance(payloads[0], PlayerAction):
        return False, "first turn event is not PlayerAction", None, None
    if not isinstance(payloads[1], DiceRolled) or "attack" not in payloads[1].reason:
        return False, "second event must be the attack DiceRolled", None, None
    if not isinstance(payloads[-1], DMNarration):
        return (
            False,
            f"last event is {type(payloads[-1]).__name__}, expected DMNarration",
            None, None,
        )

    middle = payloads[2:-1]

    if not middle:
        return True, None, False, False  # miss

    if (
        isinstance(middle[0], DiceRolled)
        and "damage" in middle[0].reason
        and len(middle) >= 2
        and isinstance(middle[1], AttributeDelta)
        and middle[1].attr == "hp"
    ):
        hit = True
        rest = middle[2:]
        downed = False
        if rest:
            if (
                len(rest) == 1
                and isinstance(rest[0], AttributeSet)
                and rest[0].attr == "status"
                and rest[0].value == "dead"
            ):
                downed = True
            else:
                return (
                    False,
                    f"unexpected events between hit mechanics and narration: "
                    f"{[type(p).__name__ for p in rest]}",
                    hit, None,
                )
        return True, None, hit, downed

    return (
        False,
        f"middle of turn doesn't match hit-or-miss pattern: "
        f"{[type(p).__name__ for p in middle]}",
        None, None,
    )


def _check_arithmetic(turn_events, pre_state, post_state, hit) -> tuple[bool, str | None, list[str]]:
    notes: list[str] = []
    attack_roll = turn_events[1].payload
    formula = attack_roll.formula

    from dice import _DICE_RE
    m = _DICE_RE.match(formula)
    if not m:
        return False, f"unparseable attack formula {formula!r}", notes
    sides = int(m.group(2))
    sign = m.group(3)
    mod_val = int(m.group(4)) if sign else 0
    if sign == "-":
        mod_val = -mod_val

    d20 = attack_roll.result - mod_val
    if not (1 <= d20 <= sides):
        return (
            False,
            f"derived d20 = {attack_roll.result} - {mod_val:+d} = {d20}, out of [1,{sides}]",
            notes,
        )
    notes.append(
        f"attack: d{sides}={d20} {mod_val:+d} = {attack_roll.result} "
        f"({'HIT' if hit else 'MISS'})"
    )

    if not hit:
        return True, None, notes

    damage_roll = turn_events[2].payload
    delta = turn_events[3].payload
    if delta.delta != -damage_roll.result:
        return (
            False,
            f"AttributeDelta.delta {delta.delta} != -damage_roll.result {-damage_roll.result}",
            notes,
        )

    target_id = delta.entity_id
    pre_hp = pre_state.entities[target_id].attributes.get("hp")
    post_hp = post_state.entities[target_id].attributes.get("hp")
    if not isinstance(pre_hp, (int, float)) or not isinstance(post_hp, (int, float)):
        return False, f"target hp is not numeric: pre={pre_hp!r}, post={post_hp!r}", notes
    if post_hp != pre_hp + delta.delta:
        return (
            False,
            f"post-replay hp {post_hp} != pre-turn hp {pre_hp} + delta {delta.delta}",
            notes,
        )
    notes.append(f"damage: {damage_roll.formula}={damage_roll.result}, hp {pre_hp} -> {post_hp}")
    return True, None, notes


def _check_replay(events) -> tuple[bool, str | None]:
    a = project(events)
    b = project(events)
    if a.model_dump_json() != b.model_dump_json():
        return False, "non-deterministic projection"
    return True, None


# ---------------------------------------------------------------------------
# Batch summary
# ---------------------------------------------------------------------------


def summarize_runs(batch_dir: Path) -> dict[str, Any]:
    """Aggregate stats across run subdirectories — input for M4+ briefs."""
    batch_dir = Path(batch_dir)
    run_dirs = sorted(p for p in batch_dir.glob("run_*") if p.is_dir())

    inspections = [inspect_run(d) for d in run_dirs]

    measurements: list[dict[str, Any]] = []
    for d in run_dirs:
        m_path = d / "measurements.json"
        if m_path.exists():
            measurements.extend(json.loads(m_path.read_text(encoding="utf-8")))

    intent_calls = [m for m in measurements if m["beat"] == "intent"]
    narration_calls = [m for m in measurements if m["beat"] == "narration"]

    return {
        "runs": len(run_dirs),
        "auto_check_pass": sum(1 for i in inspections if i.all_ok),
        "auto_check_fail": sum(1 for i in inspections if not i.all_ok),
        "succeeded_turns": sum(1 for i in inspections if i.succeeded),
        "fell_back_turns": sum(1 for i in inspections if i.fell_back),
        "fallback_breakdown": _fallback_breakdown(inspections),
        "hits": sum(1 for i in inspections if i.hit),
        "misses": sum(1 for i in inspections if i.hit is False),
        "downed": sum(1 for i in inspections if i.downed),
        "beat_intent": _beat_summary(intent_calls),
        "beat_narration": _beat_summary(narration_calls),
        "per_run_failures": [
            {"run": i.run_dir.name, "reason": i.failure_reason}
            for i in inspections
            if not i.all_ok
        ],
    }


def _fallback_breakdown(inspections) -> dict[str, int]:
    counts = {"intent": 0, "narration": 0}
    for i in inspections:
        if i.fallback_beat in counts:
            counts[i.fallback_beat] += 1
    return counts


def _beat_summary(calls: list[dict[str, Any]]) -> dict[str, Any]:
    if not calls:
        return {"calls": 0}
    parse_counts: dict[str, int] = {}
    for c in calls:
        parse_counts[c["parse_status"]] = parse_counts.get(c["parse_status"], 0) + 1

    # Per-attempt-index breakdown: how many calls were the initial attempt,
    # how many were retries, and the parse_ok rate at each index. This is
    # the M3-specific signal: are retries actually recovering, or just
    # repeating the same failure?
    by_attempt: dict[int, list[dict[str, Any]]] = {}
    for c in calls:
        by_attempt.setdefault(c.get("attempt_idx", 0), []).append(c)

    per_attempt = {}
    for idx in sorted(by_attempt):
        attempt_calls = by_attempt[idx]
        ok = sum(1 for c in attempt_calls if c["parse_status"] == "ok")
        per_attempt[str(idx)] = {
            "calls": len(attempt_calls),
            "ok": ok,
            "ok_rate": ok / len(attempt_calls),
        }

    return {
        "calls": len(calls),
        "parse_status_breakdown": parse_counts,
        "parse_ok_rate": parse_counts.get("ok", 0) / len(calls),
        "per_attempt_idx": per_attempt,
        "latency_s": _stats([c["latency_s"] for c in calls]),
        "prompt_chars": _stats([c["prompt_chars"] for c in calls]),
        "completion_chars": _stats([c["completion_chars"] for c in calls]),
    }


def _stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"median": None, "p95": None, "min": None, "max": None}
    s = sorted(values)
    n = len(s)
    p95_idx = min(n - 1, int(n * 0.95))
    return {
        "median": float(median(s)),
        "p95": float(s[p95_idx]),
        "min": float(s[0]),
        "max": float(s[-1]),
    }
