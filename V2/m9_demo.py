"""
M9 demo — demo_dungeon with full scenario coverage.

Same scaffold as m8_demo.py, but with M9-specific surfacing:
  - Live `<check/>`, `<use_item/>`, `<puzzle_answer/>` roll/use/answer
    counts printed inline
  - Countdown ticks visible in the per-turn output
  - End-of-run gate report against the M9 brief's six criteria

Operator workflow:
  1. ollama serve
  2. ollama pull qwen3:14b   (once)
  3. python m9_demo.py
"""
from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import ollama

import config
import scheduler
from dm import DMAgent
from eventlog import EventLog
from llm import DEFAULT_MODEL
from m2_inspect import MeasurementSink
from models import (
    AttributeSet,
    CombatStart,
    DiceRolled,
    DMNarration,
    EntityCreated,
    EntityMoved,
    InventoryAdded,
    InventoryRemoved,
    PlayerAction,
)
from player import PlayerAgent
from projection import project
from runner import run_npc_turn, run_turn
from seed import load_seed_file
from view_builder import build_view


HERE = Path(__file__).resolve().parent
SEED_FILE = HERE / "demo_dungeon.json"
RUNS_ROOT = HERE / "runs"


PC_IDS = ["ent_pc_brakka", "ent_pc_sylvi"]
WARDEN_ID = "ent_warden"

# Party-level mission objectives. Threaded into every PlayerAgent's
# system prompt via PlayerAgent(goals=...). The M9 runs without goals
# revealed a pattern where PCs reacted to whatever was in front of them
# (plaque, Warden, Aldous) without any pull toward the dungeon's actual
# goal — they'd spend a 25-turn budget interrogating one NPC and never
# reach the Heart Vault. These goals are the counterweight to persona-
# obedience: "Curious to a fault" balanced against "Reach the Heart
# Vault before the seal closes" gives Sylvi a reason to look at the
# plaque once and move on.
PARTY_GOALS = [
    "Descend through the dungeon to reach the Heart Vault in its depths.",
    "Retrieve the Heartstone from the Vault before the seal closes you in.",
    "Escape the dungeon alive with the party intact.",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    parser.add_argument("--max-turns", type=int, default=40)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--retry-cap", type=int, default=None)
    parser.add_argument("--skip-ollama-check", action="store_true")
    args = parser.parse_args(argv)

    if not args.skip_ollama_check and not _check_ollama(args.model):
        return 1

    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RUNS_ROOT / f"m9_{batch_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"Run dir: {run_dir}\n")

    log = EventLog(run_dir / "events.jsonl")
    load_seed_file(SEED_FILE, log)
    initial_state = project(log.events())

    print(f"Loaded demo dungeon: {len(initial_state.locations)} locations, "
          f"{len(initial_state.entities)} entities, "
          f"{len(initial_state.items)} items.")
    for pid in PC_IDS:
        e = initial_state.entities.get(pid)
        if e is not None:
            print(f"  PC {pid} ({e.display_name}) starts in {e.location_id}")
    print()

    sink = MeasurementSink(run_dir / "measurements.json")
    debug_path = run_dir / config.DEBUG_LOG_FILENAME
    rng = random.Random(args.seed) if args.seed is not None else random.Random()
    dm = DMAgent(model=args.model, retry_cap=args.retry_cap)

    player_agents: dict[str, PlayerAgent] = {}
    for pid in PC_IDS:
        entity = initial_state.entities[pid]
        persona = entity.attributes.get("persona", "")
        role = (
            f"You are {entity.display_name}. {persona} "
            f"You and your party are exploring a dungeon. Speak and act in character."
        )
        player_agents[pid] = PlayerAgent(
            player_id=pid,
            role_description=role,
            model=args.model,
            retry_cap=args.retry_cap,
            goals=PARTY_GOALS,
        )

    turns_taken = 0
    while turns_taken < args.max_turns:
        actor_id = scheduler.next_actor(log.events(), PC_IDS)
        if actor_id is None:
            print("No actor available. Stopping.")
            break

        mode = scheduler.current_mode(log.events())
        state = project(log.events())
        actor = state.entities[actor_id]
        loc = actor.location_id
        print(f"--- Turn {turns_taken + 1}  [{mode}]  actor: {actor_id} (@ {loc})")

        log_len_before = len(log.events())
        if actor_id in PC_IDS:
            _do_pc_turn(log, actor_id, player_agents[actor_id], dm, rng, sink, debug_path)
        else:
            _do_npc_turn(log, actor_id, dm, rng, sink, debug_path)

        _print_m9_events(log, log_len_before)
        turns_taken += 1
        print()

    sink.dump()
    _print_intent_breakdown(log)
    _print_rooms_visited(log)
    _print_final_state(log)
    _print_gate_report(log)
    print(f"\nLog: {run_dir / 'events.jsonl'}")
    print(f"Measurements: {run_dir / 'measurements.json'}")
    if debug_path.exists():
        print(f"Debug log: {debug_path}")
    return 0


def _do_pc_turn(log, player_id, agent, dm, rng, sink, debug_path):
    state = project(log.events())
    view = build_view(log.events(), player_id)
    short = player_id.replace("ent_pc_", "")

    turn_result = agent.act(view, state)
    intent_types = [intent.type for intent in turn_result.intents]
    if turn_result.succeeded:
        plan_str = " + ".join(intent_types) if intent_types else "(pass)"
        print(f"  {short} plans: {plan_str}")
    else:
        print(f"  {short} plan FAILED ({turn_result.parse_status}): {turn_result.error_message}")
    print(f"  {short} prose: {turn_result.narration_text}")

    result = run_turn(
        log, player_id, view.current_location_id, turn_result,
        dm, rng, sink, debug_log_path=debug_path,
    )

    if result.succeeded:
        narration = _last_narration_for(log, player_id)
        if narration:
            print(f"  DM: {narration}")
        if _new_combat_started_this_turn(log, result.turn_id):
            print(f"  >> combat_start auto-emitted")
    else:
        print(f"  DM turn FELL BACK on beat {result.fallback_beat!r}")


def _do_npc_turn(log, npc_id, dm, rng, sink, debug_path):
    state = project(log.events())
    npc = state.entities[npc_id]
    result = run_npc_turn(
        log, npc_id, npc.location_id, dm, rng, sink, debug_log_path=debug_path,
    )
    if result.succeeded:
        narration = _last_narration_for(log, npc_id)
        if narration:
            print(f"  DM (as {npc.display_name}): {narration}")
    else:
        print(f"  NPC turn FELL BACK on beat {result.fallback_beat!r}")


def _print_m9_events(log: EventLog, since: int) -> None:
    """Surface M9-relevant events that landed this turn: check rolls,
    item consumption, unlocked/solved markers, countdown ticks."""
    new_events = log.events()[since:]
    for e in new_events:
        p = e.payload
        if isinstance(p, DiceRolled):
            reason = p.reason
            if reason.startswith(("check ", "heal:", "search")):
                print(f"  >> roll: {reason} → {p.result} ({p.formula})")
        elif isinstance(p, AttributeSet):
            attr = p.attr
            if attr.startswith("countdown_") and not attr.endswith("_expired"):
                print(f"  >> countdown: {p.entity_id}.{attr} = {p.value}")
            elif attr.endswith("_expired"):
                print(f"  >> EXPIRED: {p.entity_id}.{attr}")
            elif attr.startswith(("unlocked_", "solved_", "sealed_")):
                print(f"  >> marker: {p.entity_id}.{attr} = {p.value}")
            elif attr == "movement_restricted":
                print(f"  >> restricted: {p.entity_id} cannot move ({p.value})")
        elif isinstance(p, InventoryAdded):
            print(f"  >> picked up: {p.item_id} → {p.entity_id}")
        elif isinstance(p, InventoryRemoved):
            print(f"  >> consumed: {p.item_id} from {p.entity_id}")


def _last_narration_for(log: EventLog, audience: str) -> str | None:
    for event in reversed(log.events()):
        if isinstance(event.payload, DMNarration) and event.payload.audience == audience:
            return event.payload.text
    return None


def _new_combat_started_this_turn(log: EventLog, turn_id: str) -> bool:
    return any(
        isinstance(e.payload, CombatStart) and e.cause.turn_id == turn_id
        for e in log.events()
    )


def _print_intent_breakdown(log: EventLog) -> None:
    print("\n" + "=" * 60)
    print("INTENT TYPE BREAKDOWN (across the session)")
    print("=" * 60)
    counts: Counter[str] = Counter()
    by_turn: dict[str, list] = {}
    for e in log.events():
        tid = e.cause.turn_id
        if tid:
            by_turn.setdefault(tid, []).append(e)

    for tid, events in by_turn.items():
        ptypes = [type(ev.payload).__name__ for ev in events]
        if "EntityMoved" in ptypes:
            counts["move"] += 1
        if any(
            isinstance(ev.payload, DiceRolled) and ev.payload.reason.startswith("attack:")
            for ev in events
        ):
            counts["attack"] += 1
        if any(
            isinstance(ev.payload, DiceRolled) and ev.payload.reason.startswith("check ")
            for ev in events
        ):
            counts["check"] += 1
        if any(
            isinstance(ev.payload, DiceRolled) and ev.payload.reason.startswith("heal:")
            for ev in events
        ):
            counts["use_item:heal"] += 1
        if any(
            isinstance(ev.payload, AttributeSet) and ev.payload.attr.startswith("unlocked_")
            for ev in events
        ):
            counts["use_item:lockpicking_success"] += 1
        if any(
            isinstance(ev.payload, AttributeSet) and ev.payload.attr.startswith("solved_")
            for ev in events
        ):
            counts["puzzle_answer:correct"] += 1
        if any(
            isinstance(ev.payload, AttributeSet) and ev.payload.attr.startswith("countdown_")
            and not ev.payload.attr.endswith("_expired")
            for ev in events
        ):
            counts["countdown_tick"] += 1

    for k, v in counts.most_common():
        print(f"  {k}: {v}")


def _print_rooms_visited(log: EventLog) -> None:
    print("\n" + "=" * 60)
    print("ROOMS VISITED")
    print("=" * 60)
    visited: dict[str, set[str]] = {pid: set() for pid in PC_IDS}
    for e in log.events():
        if isinstance(e.payload, EntityCreated) and e.payload.entity_id in visited:
            visited[e.payload.entity_id].add(e.payload.location_id)
        elif isinstance(e.payload, EntityMoved) and e.payload.entity_id in visited:
            visited[e.payload.entity_id].add(e.payload.to_location)
    for pid, locs in visited.items():
        short = pid.replace("ent_pc_", "")
        print(f"  {short}: {len(locs)} room(s) — {sorted(locs)}")


def _print_final_state(log: EventLog) -> None:
    print("\n" + "=" * 60)
    print("FINAL MECHANICAL STATE")
    print("=" * 60)
    state = project(log.events())
    for eid, entity in state.entities.items():
        attrs = entity.attributes
        hp = attrs.get("hp", "?")
        max_hp = attrs.get("max_hp", "?")
        status = attrs.get("status", "")
        status_str = f" [{status}]" if status else ""
        notable: list[str] = []
        for k, v in attrs.items():
            if k.startswith("countdown_") and not k.endswith("_expired"):
                notable.append(f"{k}={v}")
            elif k.endswith("_expired") and v:
                notable.append(f"{k}=True")
            elif k.startswith(("unlocked_", "solved_", "sealed_")) and v:
                notable.append(f"{k}=True")
        extra = (" " + " ".join(notable)) if notable else ""
        print(f"  {entity.display_name} (id={eid}) @ {entity.location_id}: "
              f"hp {hp}/{max_hp}{status_str}{extra}")


def _print_gate_report(log: EventLog) -> None:
    """Check the M9 brief's six gate criteria against the event log.
    Prints which criteria fired so the operator can judge the run."""
    print("\n" + "=" * 60)
    print("M9 GATE — scenario coverage")
    print("=" * 60)
    events = log.events()

    warden_engaged = any(
        (isinstance(e.payload, PlayerAction) and "warden" in e.payload.text.lower())
        or (isinstance(e.payload, DMNarration) and e.cause.player_id == WARDEN_ID)
        or (isinstance(e.payload, DiceRolled) and WARDEN_ID in e.payload.reason)
        for e in events
    )
    used_item = any(
        isinstance(e.payload, DiceRolled) and (
            e.payload.reason.startswith("heal:") or "lockpicking" in e.payload.reason
        )
        for e in events
    )
    rolled_check = any(
        isinstance(e.payload, DiceRolled) and e.payload.reason.startswith("check ")
        for e in events
    )
    solved_puzzle = any(
        isinstance(e.payload, AttributeSet) and e.payload.attr.startswith("solved_")
        for e in events
    )
    npc_talked = any(
        isinstance(e.payload, DMNarration)
        and e.cause.player_id not in PC_IDS
        and e.cause.player_id is not None
        for e in events
    )
    countdown_fired = any(
        isinstance(e.payload, AttributeSet) and e.payload.attr.startswith("countdown_")
        for e in events
    )

    criteria = [
        ("Warden engagement (negotiation or combat)", warden_engaged),
        ("≥1 <use_item/> (heal or lockpicking)", used_item),
        ("≥1 <check/> roll", rolled_check),
        ("≥1 <puzzle_answer/> solved", solved_puzzle),
        ("≥1 NPC narration (DM played an NPC turn)", npc_talked),
        ("Heartstone countdown fired", countdown_fired),
    ]
    n_met = sum(1 for _, ok in criteria if ok)
    for label, ok in criteria:
        mark = "[OK]" if ok else "[--]"
        print(f"  {mark} {label}")
    print(f"\n  {n_met}/6 criteria met "
          f"({'PASS' if n_met >= 5 else 'BELOW THRESHOLD'} — brief asks for >= 5)")


def _check_ollama(model: str) -> bool:
    try:
        listing = ollama.list()
    except Exception as e:
        print(f"ERROR: Ollama not reachable ({e.__class__.__name__}: {e})")
        print("Start the server: ollama serve")
        return False
    available = [m.model for m in listing.models]
    if model not in available:
        print(f"ERROR: model {model!r} not found locally. Pull it: ollama pull {model}")
        return False
    return True


if __name__ == "__main__":
    sys.exit(main())
