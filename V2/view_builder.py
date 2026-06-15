"""
Per-player view builder — the structural scoping boundary.

`build_view(events, player_id)` returns a `PlayerView` containing only
events the player was entitled to witness, computed by witnessed-history
scoping: at each event's `seq`, the player's location is determined from
the entity_created / entity_moved trail up to that seq, and the event is
included iff the visibility rule for its payload type allows it.

The locked guarantee from m4_build_brief.md:
**Anything `build_view` excludes is not in the returned data. Prompt
templates that render PlayerView can only reach events the builder
allowed through.** There is no prompt-instruction-based scoping path.

Per-payload visibility (locked):
  - DMNarration       : location_id matches player's location@seq OR
                        audience == player_id (the private-aside path)
  - PlayerAction      : location_id matches player's location@seq
  - SummaryCreated    : always (global summary)
  - Everything else   : never (mechanical bookkeeping or infrastructure)
"""
from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field

from goals import PartyGoal, completed_goal_ids, select_active_goal
from models import (
    DiceRolled,
    DMNarration,
    EntityCreated,
    EntityMoved,
    Event,
    PlayerAction,
    SummaryCreated,
    WorldState,
)
from projection import project


@dataclass(frozen=True)
class PlayerView:
    """The structural output of view scoping.

    `visible_events` is the load-bearing field — the gate test asserts
    that no out-of-scope event appears here. `current_location_id`,
    `summary`, `visited_locations`, and `consecutive_turns_here` are
    render conveniences (all computed from the same trail)."""

    player_id: str
    current_location_id: str
    visible_events: list[Event]
    summary: SummaryCreated | None
    visited_locations: list[str] = field(default_factory=list)
    # M9 / B2 follow-up: how many PlayerAction events this player has
    # emitted since their most recent EntityMoved (or since spawn if
    # they have never moved). Surfaced to the prompt builder so it can
    # apply room-stickiness pressure when the count gets large.
    consecutive_turns_here: int = 0
    # B2 follow-up: combat in nearby rooms on the most recent committed
    # turn. List of (graph_distance, location_id) pairs, only filled for
    # 1 <= distance <= 2 from current_location_id. Used to surface
    # "you hear fighting nearby" sound cues so PCs can choose to back up
    # an embattled ally instead of pressing solo objectives. Distance is
    # the only info leaked — entities involved are not (the M4 scoping
    # spirit holds: PCs hear the sound, not the mechanics).
    nearby_commotion: list[tuple[int, str]] = field(default_factory=list)
    # Anti-fixation: a terse digest of THIS player's own recent turns
    # (oldest→newest), consecutive identical actions collapsed to "action ×N".
    # Surfaced so the model can see — and stop — its own repetition, the main
    # driver of the observed fixation loops (e.g. re-searching the same object).
    recent_actions: list[str] = field(default_factory=list)


class ViewBuilderError(ValueError):
    """Raised when the player doesn't appear in the event log."""


# Strips seed-author meta-annotations like
# "[DEMO: COMBAT - a baseline two-enemy fight ...]" out of any text
# headed for an LLM prompt. The annotations live in the seed file as a
# convenience for the demo author but they leak game-design intent into
# the PC's view, telegraph puzzle solutions, and waste prompt budget.
# Applied at render time (not load time) so old runs render cleanly too.
_DEMO_TAG_RE = re.compile(r"\s*\[DEMO:[^\]]*\]\s*")


def strip_demo_annotations(text: str) -> str:
    """Remove `[DEMO: ...]` substrings and collapse the surrounding
    whitespace. Returns the input unchanged if no annotation is present."""
    if not isinstance(text, str) or "[DEMO:" not in text:
        return text
    return _DEMO_TAG_RE.sub(" ", text).strip()


def build_view(events: list[Event], player_id: str) -> PlayerView:
    """Single-pass filter. O(N) in the event count."""
    player_loc: str | None = None
    visible: list[Event] = []
    summary: SummaryCreated | None = None

    for event in events:
        p = event.payload

        # Update *this* player's location trail. EntityMoved / EntityCreated
        # for OTHER entities don't change our filter; we ignore them.
        if isinstance(p, EntityCreated) and p.entity_id == player_id:
            player_loc = p.location_id
        elif isinstance(p, EntityMoved) and p.entity_id == player_id:
            player_loc = p.to_location

        # Visibility filter — the structural guarantee lives in these
        # branches. Any payload type not named here is invisible.
        if isinstance(p, DMNarration):
            if p.location_id == player_loc or p.audience == player_id:
                visible.append(event)
        elif isinstance(p, PlayerAction):
            if p.location_id == player_loc:
                visible.append(event)
        elif isinstance(p, SummaryCreated):
            visible.append(event)
            summary = p  # keep the most recent

    if player_loc is None:
        raise ViewBuilderError(
            f"player {player_id!r} has no entity_created in the event log"
        )

    # M6: events covered by the latest summary are dropped from
    # visible_events (the summary's text already covers them — keeping
    # them would just bloat the prompt). The SummaryCreated event
    # itself is always retained so render_for_prompt + M4's G4 test
    # still see it.
    if summary is not None:
        cutoff = summary.covers_through
        visible = [
            e for e in visible
            if e.seq > cutoff or isinstance(e.payload, SummaryCreated)
        ]

    # M8.1: compute the player's ordered list of visited locations from
    # the same event walk used above (only this player's create + move
    # events). The view exposes this so render_for_prompt can show the
    # discovered dungeon graph — without leaking unvisited rooms.
    visited_locations = _compute_visited_locations(events, player_id)

    # B2 follow-up: consecutive turns this player has been in their
    # current room (no intervening move). Used by build_player_prompt
    # to apply room-stickiness pressure when the count gets high.
    consecutive_turns_here = _count_consecutive_turns_in_current_room(
        events, player_id,
    )

    # B2 follow-up: nearby combat sounds. Computed only after we know
    # player_loc; needs the projected state for the location graph.
    state = project(events)
    nearby_commotion = compute_nearby_commotion(events, player_loc, state)

    # Anti-fixation digest of the player's own recent turns.
    recent_actions = _compute_recent_actions(events, player_id)

    return PlayerView(
        player_id=player_id,
        current_location_id=player_loc,
        visible_events=visible,
        summary=summary,
        visited_locations=visited_locations,
        consecutive_turns_here=consecutive_turns_here,
        nearby_commotion=nearby_commotion,
        recent_actions=recent_actions,
    )


# Priority when one turn carries several mechanical events — the most
# fixation-relevant action wins the turn's label (a repeated check/attack
# matters more than the move that ended the turn; bare prose is weakest).
_ACTION_PRIORITY = {"check": 3, "attack": 3, "move": 2, "spoke": 1}


def _compute_recent_actions(
    events: list[Event], player_id: str, limit: int = 6,
) -> list[str]:
    """Terse digest of `player_id`'s own recent turns (oldest→newest, last
    `limit`), consecutive identical actions collapsed to "action ×N".

    Derived from the player's committed mechanical events (moves, checks,
    attacks); a turn with only prose reads as "spoke / roleplayed". Per-player
    by construction (cause.player_id) — no cross-PC scope leak."""
    turn_order: list[str] = []
    best: dict[str, tuple[int, str]] = {}  # turn_id -> (priority, label)
    for e in events:
        if e.cause.player_id != player_id or not e.cause.turn_id:
            continue
        tid = e.cause.turn_id
        if tid not in best:
            turn_order.append(tid)
            best[tid] = (0, "")
        p = e.payload
        prio, label = 0, None
        if isinstance(p, DiceRolled) and (p.reason or "").startswith("check"):
            target = p.reason.split("->")[-1].strip()
            m = re.search(r"check\s+'([^']*)'", p.reason)
            purpose = m.group(1) if (m and m.group(1)) else "check"
            prio, label = _ACTION_PRIORITY["check"], f"{purpose} check on {target}"
        elif isinstance(p, DiceRolled) and (p.reason or "").startswith("attack:"):
            target = p.reason.split("->")[-1].strip()
            prio, label = _ACTION_PRIORITY["attack"], f"attacked {target}"
        elif isinstance(p, EntityMoved) and p.entity_id == player_id:
            prio, label = _ACTION_PRIORITY["move"], f"moved to {p.to_location}"
        elif isinstance(p, PlayerAction):
            prio, label = _ACTION_PRIORITY["spoke"], "spoke / roleplayed"
        if label is not None and prio > best[tid][0]:
            best[tid] = (prio, label)

    labels = [best[t][1] for t in turn_order if best[t][1]][-limit:]
    collapsed: list[list] = []
    for lab in labels:
        if collapsed and collapsed[-1][0] == lab:
            collapsed[-1][1] += 1
        else:
            collapsed.append([lab, 1])
    return [f"{lab} ×{n}" if n > 1 else lab for lab, n in collapsed]


def _count_consecutive_turns_in_current_room(
    events: list[Event],
    player_id: str,
) -> int:
    """Count PlayerAction events emitted by `player_id` since their
    most recent EntityMoved (or since spawn if they have never moved).

    Per-PC player_actions are always at the PC's current location at
    emit time, so this is equivalently the number of turns the PC has
    spent in their current room without moving. Used to drive the
    room-stickiness pressure clause."""
    last_move_seq = -1
    for e in events:
        p = e.payload
        if isinstance(p, EntityMoved) and p.entity_id == player_id:
            if e.seq > last_move_seq:
                last_move_seq = e.seq
    count = 0
    for e in events:
        if e.seq <= last_move_seq:
            continue
        p = e.payload
        if isinstance(p, PlayerAction) and p.player_id == player_id:
            count += 1
    return count


def compute_nearby_commotion(
    events: list[Event],
    current_location_id: str,
    state: WorldState,
    max_distance: int = 2,
) -> list[tuple[int, str]]:
    """Detect combat happening in nearby rooms on the most recent
    committed turn. Returns (graph_distance, location_id) tuples for
    each combat location with 1 <= distance <= max_distance from
    `current_location_id`.

    The PC's OWN room is excluded — combat there shows up in
    [Recent events] and the affordances block; we don't want to also
    label it as "nearby". The cue is for hearing combat through walls.

    Distance is the only information leaked across the M4 scoping
    boundary; entity identities involved in the fight are not, in the
    spirit of TTRPG audio — you hear the clash, not the names. The
    M4 G1 invariant covers events, not derived distance signals."""
    last_turn_id: str | None = None
    for e in reversed(events):
        if e.cause.turn_id:
            last_turn_id = e.cause.turn_id
            break
    if last_turn_id is None:
        return []

    combat_loc: str | None = None
    saw_combat_dice = False
    for e in events:
        if e.cause.turn_id != last_turn_id:
            continue
        p = e.payload
        if isinstance(p, DiceRolled):
            reason = (p.reason or "").lower()
            if reason.startswith("attack:") or reason.startswith("damage:"):
                saw_combat_dice = True
        elif isinstance(p, DMNarration):
            # The turn's narration carries the location where the actor
            # acted. (NPC turns produce one DMNarration whose location
            # is the NPC's; PC turns same shape.)
            combat_loc = p.location_id

    if not saw_combat_dice or not combat_loc:
        return []
    if combat_loc == current_location_id:
        return []

    distance = _graph_distance(state, current_location_id, combat_loc, max_distance)
    if distance is None or distance < 1 or distance > max_distance:
        return []

    return [(distance, combat_loc)]


def _graph_distance(
    state: WorldState,
    from_id: str,
    to_id: str,
    max_d: int,
) -> int | None:
    """BFS shortest-path hop count between two locations. Returns None
    if `to_id` is not reachable within `max_d` hops (or not reachable
    at all). Locations are nodes; connections are undirected edges."""
    if from_id == to_id:
        return 0
    if from_id not in state.locations or to_id not in state.locations:
        return None
    visited: set[str] = {from_id}
    frontier: list[str] = [from_id]
    for d in range(1, max_d + 1):
        next_frontier: list[str] = []
        for loc_id in frontier:
            loc = state.locations.get(loc_id)
            if loc is None:
                continue
            for nxt in loc.connections:
                if nxt in visited:
                    continue
                if nxt == to_id:
                    return d
                visited.add(nxt)
                next_frontier.append(nxt)
        frontier = next_frontier
        if not frontier:
            return None
    return None


def _bfs_next_hop(
    state: WorldState,
    from_id: str,
    to_id: str,
    allowed: set[str] | None = None,
) -> str | None:
    """The first hop on a shortest path from `from_id` to `to_id` — i.e.
    the directly-connected room to step toward. When `allowed` is given,
    only those location ids may appear on the path (including `to_id`), so
    a visited-only set restricts the search to fully-known territory.
    Returns None if `to_id` is unreachable under the constraint.

    Connections are explored in sorted order so the chosen hop is
    deterministic (replay-stable, test-friendly) when several shortest
    paths tie."""
    if from_id == to_id:
        return None
    if from_id not in state.locations or to_id not in state.locations:
        return None
    seen: set[str] = {from_id}
    # Queue entries carry the first hop taken from `from_id` so we can
    # report it the moment we reach the target.
    queue: deque[tuple[str, str | None]] = deque([(from_id, None)])
    while queue:
        cur, first = queue.popleft()
        cur_loc = state.locations.get(cur)
        if cur_loc is None:
            continue
        for nxt in sorted(cur_loc.connections):
            if nxt in seen:
                continue
            if allowed is not None and nxt not in allowed:
                continue
            hop = nxt if first is None else first
            if nxt == to_id:
                return hop
            seen.add(nxt)
            queue.append((nxt, hop))
    return None


def navigation_hint(
    state: WorldState,
    current_id: str,
    target_id: str,
    visited: list[str] | set[str],
) -> tuple[str, str | None] | None:
    """Decide which direction points toward `target_id`, respecting what
    the player actually knows (their `visited` set). Returns a
    `(kind, hop)` pair, or None when no hint applies:

      - ("here", None)       — the player is already at the target.
      - ("known", hop)       — `hop` is a visited room to step toward; the
                               route there is (at least its next step)
                               known territory.
      - ("frontier", hop)    — the way is not yet charted; `hop` is the
                               unexplored exit on the true path toward the
                               goal. We reveal only "explore that way", not
                               what lies behind it.

    Policy ("middle" disclosure): prefer a fully-known route when one
    exists (never push the party into the unknown if they already know the
    way). Only when no fully-visited route exists do we consult the true
    map to pick the single frontier door that actually makes progress."""
    if target_id not in state.locations:
        return None
    if current_id == target_id:
        return ("here", None)
    visited_set = set(visited)

    # 1. Fully-known route: the target is somewhere the player has been,
    #    reachable without stepping through any unexplored room.
    if target_id in visited_set:
        hop = _bfs_next_hop(state, current_id, target_id, allowed=visited_set)
        if hop is not None:
            return ("known", hop)

    # 2. Uncharted: fall back to the true graph for the next hop toward the
    #    target. Naming respects fog-of-war — a visited next room is named,
    #    an unexplored one is only pointed at.
    hop = _bfs_next_hop(state, current_id, target_id, allowed=None)
    if hop is None:
        return None
    if hop in visited_set:
        return ("known", hop)
    return ("frontier", hop)


def _compute_visited_locations(events: list[Event], player_id: str) -> list[str]:
    """Walk the log for the player's location history. Returns the
    ordered list of distinct location_ids the player has been in
    (first-visit order). Used by render_for_prompt to surface the
    discovered dungeon graph as spatial memory.

    M4 G1 invariant carries: a location appears here ONLY if the
    player was structurally in it (their EntityCreated or a subsequent
    EntityMoved put them there). Rooms in the world the player has
    never visited do NOT appear."""
    order: list[str] = []
    seen: set[str] = set()
    for event in events:
        p = event.payload
        loc_id: str | None = None
        if isinstance(p, EntityCreated) and p.entity_id == player_id:
            loc_id = p.location_id
        elif isinstance(p, EntityMoved) and p.entity_id == player_id:
            loc_id = p.to_location
        if loc_id is not None and loc_id not in seen:
            order.append(loc_id)
            seen.add(loc_id)
    return order


def render_for_prompt(
    view: PlayerView,
    state: WorldState,
    goals: list[PartyGoal] | None = None,
) -> str:
    """
    Format `view` into a prose block suitable for the player's LLM prompt.

    `state` supplies the names/descriptions of locations + entities (the
    view only carries event references; render time is when we look up
    human-readable details). This split keeps the structural test (on
    `visible_events`) decoupled from text formatting.

    Ordering (top → bottom):
      1. [Story so far] — older narrative summary
      2. [Recent events] — newest narrative beats (paired with summary
         so the LLM reads narrative context as one block)
      3. [You are in <loc>] + description — current scene
      4. Present with you — immediate social context
      5. [You hear from nearby] — nearby commotion cues
      6. [Your status] + countdowns
      7. [Party] — other PCs' last-known location + HP
      8. [Tactical] — urgent cues (wounded + heal item, etc.)
      9. [Rooms you have explored] + frontier — navigation memory
     10. [Party objective] — goals + a directional hint toward the active
         one (only when `goals` is supplied)
     11. [Affordances] — decision menu (placed near the end so the
         LLM has the option list fresh when asked "what do you do?")
    """
    lines: list[str] = []
    me = state.entities.get(view.player_id)

    if view.summary is not None:
        lines.append("[Story so far]")
        lines.append(view.summary.text)
        lines.append("")

    # Recent events live with [Story so far] — both are narrative-time
    # context. Previously this block was placed mid-scene (after
    # "Present with you"), which broke the temporal flow.
    if view.visible_events:
        lines.append("[Recent events]")
        for event in view.visible_events:
            p = event.payload
            if isinstance(p, PlayerAction):
                # The viewer's OWN actions are already in the terse
                # [Your recent actions] digest — echoing the full prose here is
                # redundant and feeds repetition, so skip them. A teammate's
                # action witnessed in the same room is NOT redundant (it's
                # party-awareness / voice), so keep those.
                if p.player_id == view.player_id:
                    continue
                speaker = state.entities.get(p.player_id)
                name = speaker.display_name if speaker else p.player_id
                lines.append(f'{name}: "{p.text}"')
            elif isinstance(p, DMNarration):
                lines.append(f"DM: {p.text}")
            # SummaryCreated already rendered at the top; do not repeat.
        lines.append("")

    location = state.locations.get(view.current_location_id)
    if location is not None:
        lines.append(f"[You are in {location.name}.]")
        lines.append(strip_demo_annotations(location.description))
        # Once a room's puzzle is solved (by anyone), the riddle text in the
        # static description is stale — and an LLM that keeps reading it will
        # keep "solving" it in circles instead of moving on (observed at the
        # cinder gate: solved on turn 41, still debating the answer at turn
        # 50). A loud, positive cue retires the puzzle in the model's view.
        if _location_puzzle_solved(state, view.current_location_id):
            lines.append(
                "[✓ SOLVED — you have already spoken the word and this "
                "threshold stands open. There is nothing left to puzzle out "
                "or discuss here; simply move on through to proceed.]"
            )
    else:
        lines.append(f"[You are in {view.current_location_id}.]")

    # Retry-safe steer for a hard gate: if an exit here is sealed behind an
    # unsolved puzzle, make the solving intent unmissable (placed in-scene so
    # the model reads it alongside where it is and can't loop on `move`).
    for steer in _render_sealed_exit_steer(state, view.current_location_id):
        lines.append(steer)

    others_present = [
        e for e in state.entities.values()
        if e.location_id == view.current_location_id and e.entity_id != view.player_id
    ]
    if others_present:
        lines.append("")
        lines.append("Present with you:")
        for e in others_present:
            status = e.attributes.get("status")
            # Hostile must be loud — it's the most consequential signal
            # for a turn plan. Friendly/neutral statuses surface too but
            # less aggressively. Absent status = no marker.
            if status == "hostile":
                tag = " — HOSTILE"
            elif status:
                tag = f" ({status})"
            else:
                tag = ""
            # M12: surface conditions (prone/poisoned/…) — they change how an
            # attack against this entity resolves, so the model should see them.
            conds = e.attributes.get("conditions")
            if isinstance(conds, list) and conds:
                tag += f" [{', '.join(str(c) for c in conds)}]"
            lines.append(f"  - {e.display_name}{tag}")

    # B2 follow-up: nearby combat sound cues. Only the distance + the
    # location id leak across the scoping boundary — not the entities
    # fighting. The point is to signal "an ally may need help in a
    # nearby room" so a PC can choose to redirect from solo objectives.
    if view.nearby_commotion:
        lines.append("")
        lines.append("[You hear from nearby]")
        for distance, loc_id in view.nearby_commotion:
            if distance == 1:
                cue = (
                    f"From {loc_id} (the next room over): the clash of "
                    f"weapons and shouting — combat is happening there."
                )
            else:
                cue = (
                    f"From {loc_id} ({distance} rooms away): muffled "
                    f"sounds of fighting drift through the stone."
                )
            lines.append(f"  {cue}")

    if me is not None:
        hp = me.attributes.get("hp")
        max_hp = me.attributes.get("max_hp")
        if isinstance(hp, (int, float)) and isinstance(max_hp, (int, float)):
            lines.append("")
            status_bits = [f"hp {hp}/{max_hp}"]
            # M9 follow-up: surface currency balances (numeric attrs
            # used by the trade resolver). "coin" is the standard
            # currency name; other named currencies show too.
            coin = me.attributes.get("coin")
            if isinstance(coin, (int, float)) and not isinstance(coin, bool):
                status_bits.append(f"coin {int(coin)}")
            # M12: your own conditions (they impose disadvantage on your rolls).
            my_conds = me.attributes.get("conditions")
            if isinstance(my_conds, list) and my_conds:
                status_bits.append("conditions: " + ", ".join(str(c) for c in my_conds))
            lines.append(f"[Your status: {', '.join(status_bits)}]")
        # M9: surface countdown_* attributes (e.g. countdown_heartstone_escape
        # = 3) so the player sees their timer pressure.
        countdowns = sorted(
            (k, v) for k, v in me.attributes.items()
            if k.startswith("countdown_")
            and not k.endswith("_expired")
            and isinstance(v, (int, float)) and not isinstance(v, bool)
        )
        if countdowns:
            for attr_name, value in countdowns:
                expired = me.attributes.get(f"{attr_name}_expired")
                tag = " — EXPIRED" if expired else ""
                lines.append(f"[Timer: {attr_name} = {int(value)}{tag}]")

    # Party block — other PCs' last-known location and HP. Strict per-PC
    # scoping (M4) prevents the player from seeing what their teammate
    # said in a distant room, but a party of adventurers obviously knows
    # roughly where their friend is and whether they're hurt. Surfacing
    # this gives the LLM a coordination signal: in M9 runs without it,
    # Sylvi never went back to help Brakka through a 17-turn skeleton
    # fight because she had no way to know he was in trouble.
    party_lines = _render_party_block(view, state)
    if party_lines:
        lines.append("")
        lines.extend(party_lines)

    # Tactical cue — a one-liner pointing the LLM at the most urgent
    # action it has the resources to take. Currently fires when the
    # actor is below half HP AND carries an inventory item that can
    # heal. Cheap to add others (low-HP + adjacent ally, hostile-in-
    # room + weapon-equipped) as patterns emerge.
    tactical_lines = _render_tactical_cues(view, state)
    if tactical_lines:
        lines.append("")
        lines.extend(tactical_lines)

    # M8.1: spatial memory — surface every visited location + its
    # connections so the player has a discovered-map view of the
    # dungeon instead of having to reconstruct geography each turn
    # from prose.
    visited_block = _render_visited_rooms(view, state)
    if visited_block:
        lines.append("")
        lines.append(visited_block)

    # M10: party objective + a single directional navigation hint toward
    # the active goal. Placed right after the discovered-map block so the
    # "head toward loc_x" line reads against the map the player just saw,
    # and just before the affordances so the objective is fresh when the
    # action menu is presented. Only rendered when goals are supplied.
    if goals:
        goal_lines = _render_goals_block(view, state, goals)
        if goal_lines:
            lines.append("")
            lines.extend(goal_lines)

    # Anti-fixation: the player's own recent actions, collapsed (×N), placed
    # right before the decision menu so the model sees its repetition just as
    # it chooses. One line, dot-separated — cheap on tokens.
    if view.recent_actions:
        lines.append("")
        # Detect a fixation loop: the digest collapses consecutive repeats to
        # "… ×N", so a high N means the player keeps doing the same thing. When
        # that happens, escalate from the soft reminder to a hard STOP keyed on
        # the exact repeated action — this is the failure mode (e.g. searching
        # the same item 3+ times) the soft line wasn't catching. Fires only
        # during an actual loop, so it costs nothing on a healthy run.
        _worst, _max_rep = "", 0
        for _entry in view.recent_actions:
            _m = re.search(r"×(\d+)\s*$", _entry)
            _n = int(_m.group(1)) if _m else 1
            if _n > _max_rep:
                _max_rep, _worst = _n, re.sub(r"\s*×\d+\s*$", "", _entry)
        if _max_rep >= 4:
            lines.append(
                f"[STOP — you are repeating yourself] You have already done "
                f"the same thing ({_worst}) {_max_rep} times with no new "
                f"result. Doing it again will NOT work and wastes the turn. "
                f"This turn do something DIFFERENT: move to a connected room, "
                f"use a different kind of action, or act toward your objective "
                f"somewhere else — not the same action on the same target."
            )
        else:
            lines.append(
                "[Your recent actions — don't just repeat these; "
                "a repeated check/talk on the same target rarely reveals more]"
            )
        lines.append("  " + " · ".join(view.recent_actions))

    # M8: append the affordances block so the player prompt can list
    # exactly which ids are valid for each intent type. Without this,
    # the model has to infer affordances from the scene description —
    # which is the M7-demo bias toward `inspect`.
    affordances = _render_affordances(view, state)
    if affordances:
        lines.append("")
        lines.append(affordances)

    return "\n".join(lines)


def _render_party_block(view: PlayerView, state: WorldState) -> list[str]:
    """Return lines describing every PC other than the viewer — their
    last-known room (from projected state, not witnessed) and HP.

    Strict per-PC event scoping (M4 G1) is unaffected: we read the
    current world state, not other PCs' visible_events. The fiction
    justifies this: party members travel together initially and know
    roughly where their friend was last seen — even if they split up,
    "the half-orc went to the guardroom" is not a TTRPG secret. The
    information also matters mechanically: without it the LLM cannot
    decide to back up an embattled ally.
    """
    others: list = []
    for entity in state.entities.values():
        if entity.kind != "pc":
            continue
        if entity.entity_id == view.player_id:
            continue
        others.append(entity)
    if not others:
        return []
    lines = ["[Party]"]
    for pc in sorted(others, key=lambda e: e.entity_id):
        loc_id = pc.location_id
        loc = state.locations.get(loc_id)
        loc_name = loc.name if loc is not None else loc_id
        hp = pc.attributes.get("hp", "?")
        max_hp = pc.attributes.get("max_hp", "?")
        status = pc.attributes.get("status")
        status_tag = ""
        if status == "dead":
            status_tag = " — DOWNED"
        elif status:
            status_tag = f" ({status})"
        same_room_marker = " (with you)" if loc_id == view.current_location_id else ""
        lines.append(
            f"  {pc.display_name} — in {loc_name} ({loc_id})"
            f"{same_room_marker}, hp {hp}/{max_hp}{status_tag}"
        )
    return lines


def _render_tactical_cues(view: PlayerView, state: WorldState) -> list[str]:
    """One-line situational hints derived from current state. Each cue
    points at an action whose resources the actor already has, so the
    LLM does not have to discover the link from raw affordances.

    Currently:
      - Below half HP + a heal-use item in inventory → name the item.

    Cues here must be HINTS, not commands — phrased to inform rather
    than to override the player's persona-driven choice.
    """
    me = state.entities.get(view.player_id)
    if me is None:
        return []
    hp = me.attributes.get("hp")
    max_hp = me.attributes.get("max_hp")
    if not (isinstance(hp, (int, float)) and isinstance(max_hp, (int, float))):
        return []
    if max_hp <= 0:
        return []

    cues: list[str] = []
    if hp <= max_hp / 2:
        heal_items: list[str] = []
        for item_id in (me.inventory or []):
            it = state.items.get(item_id)
            if it is None:
                continue
            if it.properties.get("use") == "heal":
                heal_items.append(item_id)
        if heal_items:
            items_csv = ", ".join(heal_items)
            cues.append(
                f"[Tactical] You are below half HP ({int(hp)}/{int(max_hp)}) "
                f"and carry a healing item: {items_csv}. Consider "
                f"<intent type=\"use_item\" item=\"{heal_items[0]}\" "
                f"target=\"{view.player_id}\"/>."
            )
    return cues


def _active_countdown_turns(state: WorldState) -> int | None:
    """The smallest live countdown across the party, or None if no timer is
    running. A countdown is live when its `countdown_*` attribute is > 0 and
    its `_expired` companion is not set. Used only for the urgent hint's
    flavor ("the seal is closing — N turns left")."""
    best: int | None = None
    for ent in state.entities.values():
        for k, v in ent.attributes.items():
            if not k.startswith("countdown_") or k.endswith("_expired"):
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                continue
            if v <= 0 or ent.attributes.get(f"{k}_expired"):
                continue
            best = int(v) if best is None else min(best, int(v))
    return best


def _solved_by_party(state: WorldState, target_id: str) -> bool:
    """True if any entity carries a `solved_<target_id>` marker. Puzzle
    solves are recorded per-actor (AttributeSet on the solver), but a door
    that opened for one PC is open for the whole party — so the view treats
    the solve as party-wide. Without this, a PC who didn't personally speak
    the word still sees the riddle as unsolved and re-engages it."""
    marker = f"solved_{target_id}"
    return any(bool(e.attributes.get(marker)) for e in state.entities.values())


def _location_puzzle_solved(state: WorldState, loc_id: str) -> bool:
    loc = state.locations.get(loc_id)
    if loc is None or not isinstance(loc.attributes.get("puzzle_answer"), str):
        return False
    return _solved_by_party(state, loc_id)


def _render_sealed_exit_steer(state: WorldState, loc_id: str) -> list[str]:
    """Retry-safe steer for a hard gate (runner `gated_exits`). When the current
    room seals an exit behind an unsolved puzzle, point the model STRAIGHT at the
    solving intent — a model that keeps trying to `move` (or narrate) through a
    sealed exit would otherwise stall here. We name the mechanism, not the answer
    (the answer lives in the riddle + the clues the party has found)."""
    loc = state.locations.get(loc_id)
    if loc is None:
        return []
    gated = loc.attributes.get("gated_exits")
    if not isinstance(gated, dict):
        return []
    out: list[str] = []
    for dest, required in gated.items():
        if not isinstance(required, str) or _solved_by_party(state, required):
            continue
        dest_loc = state.locations.get(dest)
        dest_name = dest_loc.name if dest_loc is not None else dest
        out.append(
            f"[⛔ SEALED EXIT — the only way on is to solve the puzzle here]\n"
            f"The way to {dest_name} ({dest}) is barred. It will NOT open by "
            f"moving toward it or by narrating the door open — the slab answers "
            f"only to the spoken word. Speak the answer with the exact intent:\n"
            f'  <intent type="puzzle_answer" target="{required}" answer="<the word the riddle calls for>"/>'
        )
    return out


def _format_navigation_hint(
    state: WorldState,
    hint: tuple[str, str | None] | None,
    urgent: bool,
    countdown: int | None = None,
) -> str | None:
    """Render a `navigation_hint` result into one player-facing line, or
    None if there's nothing to say.

    Tone is urgency-aware (M10): while the active objective is an ordinary
    milestone the hint is a *soft compass* that explicitly licenses
    exploring along the way — this is where the dungeon's side content
    (checks, puzzles, NPCs) lives, and a commanding hint made the party
    beeline past all of it. Only once the objective is a terminal/escape
    goal (carrying the macguffin out, a seal closing) does the hint become
    a firm directive.

    Visited rooms are named (the player has been there); unexplored exits
    are referred to by id only — the same fog-of-war convention the Frontier
    block uses."""
    if hint is None:
        return None
    kind, hop = hint
    loc = state.locations.get(hop) if hop else None
    name = (loc.name if loc is not None else hop)

    if urgent:
        timer = (
            f" The seal is closing — {countdown} turn(s) left."
            if countdown is not None else ""
        )
        if kind == "here":
            return "↳ ESCAPE: you are at the exit — get clear now."
        if kind == "known":
            return f"↳ ESCAPE: head for {name} ({hop}) now.{timer}"
        if kind == "frontier":
            return (
                f"↳ ESCAPE: the way out is the unexplored passage from here "
                f"({hop}) — take it now.{timer}"
            )
        return None

    # Non-urgent: a relaxed compass that invites exploration.
    if kind == "here":
        return "↳ You have reached this objective."
    if kind == "known":
        return (
            f"↳ Your objective lies onward, roughly via {name} ({hop}). "
            f"No rush — nearby rooms may be worth exploring first."
        )
    if kind == "frontier":
        return (
            f"↳ Your objective lies deeper, past an unexplored passage from "
            f"here ({hop}). No rush — explore nearby rooms along the way if "
            f"you wish."
        )
    return None


def _render_goals_block(
    view: PlayerView, state: WorldState, goals: list[PartyGoal]
) -> list[str]:
    """The per-turn [Party objective] block. Lists every goal's text (a ✓
    on completed ones) so the party always sees the whole plan, and attaches
    a single directional navigation hint to the one currently-active goal.

    The active goal and its completion state are *derived* from current
    world state (see goals.py), so the block reacts to play automatically:
    grab the Heartstone and the escape goal activates, its route appears,
    and the earlier goals show as done — no event, no special-casing."""
    if not goals:
        return []
    active = select_active_goal(goals, state)
    done_ids = completed_goal_ids(goals, state)
    # Urgency = the active objective is a terminal/escape goal (gated on
    # carrying something out). This persists through the whole flight, even
    # after a countdown hits zero — which is what keeps the firm hint up
    # until the party is actually clear. The countdown, when live, only
    # adds flavor.
    urgent = active is not None and active.requires_item_held is not None
    countdown = _active_countdown_turns(state) if urgent else None
    out: list[str] = ["[Party objective]"]
    for g in goals:
        mark = "  ✓ (done)" if g.id in done_ids else ""
        out.append(f"  - {g.text}{mark}")
        if g is active and g.target_location:
            hint = navigation_hint(
                state, view.current_location_id, g.target_location,
                view.visited_locations,
            )
            line = _format_navigation_hint(state, hint, urgent, countdown)
            if line:
                out.append(f"      {line}")
    return out


def _render_visited_rooms(view: PlayerView, state: WorldState) -> str:
    """Compact spatial memory (M11 prompt-trim): a one-line list of explored
    room ids (current room marked) + a one-line list of still-unexplored exits
    reachable from explored rooms.

    The old block rendered the full per-room connectivity graph every turn
    (~25% of the late-game prompt). That was largely redundant: the navigation
    hint already computes the route to the objective, and the Move affordance
    lists the current room's exits — so the verbose graph mostly fed prompt
    bloat and decision noise. We keep only what the model can't get elsewhere:
    which rooms it has seen, and which exits remain unexplored.

    M4 G1 still holds: only this player's visited rooms appear, and the frontier
    names only exit ids one hop out (the same fog-of-war disclosure as before —
    contents stay unknown until entered)."""
    if not view.visited_locations:
        return ""
    visited_set: set[str] = set(view.visited_locations)
    rooms = ", ".join(
        f"{loc_id}{' (you are here)' if loc_id == view.current_location_id else ''}"
        for loc_id in view.visited_locations
    )
    lines = [f"[Map — {len(view.visited_locations)} rooms explored]", f"  {rooms}"]

    frontier: list[str] = []
    for loc_id in view.visited_locations:
        loc = state.locations.get(loc_id)
        if loc is None:
            continue
        for exit_id in loc.connections:
            if exit_id not in visited_set and exit_id not in frontier:
                frontier.append(exit_id)
    if frontier:
        lines.append(
            "  Unexplored exits (contents unknown until you enter): "
            + ", ".join(sorted(frontier))
        )
    return "\n".join(lines)


def _render_affordances(view: PlayerView, state: WorldState) -> str:
    """
    Build the M8 affordances block: lists of valid ids per intent type
    (move, look/examine, attack, talk) plus a short action-economy
    reminder. The PlayerAgent prompt uses this directly so the model
    sees concrete ids instead of having to invent them.
    """
    loc = state.locations.get(view.current_location_id)
    actor = state.entities.get(view.player_id)
    if loc is None or actor is None:
        return ""  # defensive; render_for_prompt already handled missing loc

    other_entities_here = [
        e for e in state.entities.values()
        if e.location_id == view.current_location_id and e.entity_id != view.player_id
    ]
    items_here = [
        i for i in state.items.values()
        if i.location_id == view.current_location_id
    ]
    inventory_items = [
        state.items[item_id] for item_id in actor.inventory
        if item_id in state.items
    ]

    # Split entities by hostility for the attack/talk hint. Either list
    # is *suggestive* not constraining — the runner allows either intent
    # on any present entity. The split helps the model pick canonically.
    hostile_entities = [
        e for e in other_entities_here
        if e.attributes.get("status") == "hostile"
    ]
    non_hostile_entities = [
        e for e in other_entities_here
        if e.attributes.get("status") != "hostile"
    ]

    out: list[str] = ["[Affordances — what you can do this turn]"]

    # Move — always render. The frontier matters even when there's "only
    # one connection" because that one connection is the way forward.
    if loc.connections:
        conns = ", ".join(sorted(loc.connections))
        out.append(f"  Move (1/turn): <intent type=\"move\" target=\"<id>\"/>")
        out.append(f"    Connected: {conns}")
    else:
        out.append(f"  Move: (no connections from here)")

    # Look — always render (the room itself is always lookable).
    look_ids: list[str] = [view.current_location_id]
    look_ids += [e.entity_id for e in other_entities_here]
    look_ids += [i.item_id for i in items_here]
    look_ids += [i.item_id for i in inventory_items]
    look_csv = ", ".join(look_ids) if look_ids else "(nothing in particular)"
    out.append(f"  Look (free, unlimited): <intent type=\"look\" target=\"<id>\"/>")
    out.append(f"    Visible: {look_csv}")

    # Examine — same id space as look; one terse line, no separate target list.
    out.append(
        f"  Examine (1 action/turn): <intent type=\"examine\" target=\"<id>\"/>  "
        f"(same ids as look; reveals hidden details)"
    )

    # Below: only render an intent section when it has at least one valid
    # target in this scene. Otherwise we emit a dense affordances block
    # full of "(no X here)" lines that dilute the signals the model
    # actually needs to act on. The model has already seen the full
    # intent vocabulary in the system suffix.

    # Attack
    if hostile_entities:
        atk_csv = ", ".join(e.entity_id for e in hostile_entities)
        out.append(f"  Attack (1 action/turn): <intent type=\"attack\" target=\"<id>\"/>")
        out.append(f"    Hostile targets here: {atk_csv}")

    # Talk
    if non_hostile_entities:
        talk_csv = ", ".join(e.entity_id for e in non_hostile_entities)
        out.append(f"  Talk (free): <intent type=\"talk\" target=\"<id>\">speech</intent>")
        out.append(f"    Present (non-hostile): {talk_csv}")

    # Pickup
    pickupable: list[str] = []
    for itm in items_here:
        if itm.item_id in (actor.inventory or []):
            continue
        item_type = itm.properties.get("type")
        if isinstance(item_type, str) and item_type in {"container", "lock", "fixture"}:
            continue
        pickupable.append(itm.item_id)
    if pickupable:
        out.append(
            f"  Pickup (1 action/turn): <intent type=\"pickup\" target=\"<item_id>\"/>"
        )
        out.append(f"    Items here you can pick up: {', '.join(pickupable)}")

    # Give — both an inventory item AND a recipient must exist.
    if inventory_items and other_entities_here:
        out.append(
            f"  Give (1 action/turn): <intent type=\"give\" "
            f"item=\"<item_id>\" target=\"<entity_id>\"/>"
        )
        inv_csv = ", ".join(i.item_id for i in inventory_items)
        tgt_csv = ", ".join(e.entity_id for e in other_entities_here)
        out.append(f"    Your items: {inv_csv}")
        out.append(f"    Recipients here: {tgt_csv}")

    # Open — only when there's a container in scene.
    containers_here = [
        i for i in items_here
        if i.properties.get("type") == "container"
    ]
    if containers_here:
        out.append(
            f"  Open (1 action/turn): <intent type=\"open\" target=\"<container_id>\"/>"
        )
        for c in containers_here:
            locked = bool(c.properties.get("locked"))
            unlocked_marker = bool(actor.attributes.get(f"unlocked_{c.item_id}"))
            opened_marker = bool(actor.attributes.get(f"opened_{c.item_id}"))
            if opened_marker:
                state_str = "already opened"
            elif locked and not unlocked_marker:
                state_str = "locked — pick the lock first"
            else:
                state_str = "unlocked, ready to open"
            out.append(f"    {c.item_id} ({c.name}) — {state_str}")

    # Trade — only when at least one merchant is present.
    traders_here: list[tuple] = []
    for e in other_entities_here:
        priced = []
        for item_id in (e.inventory or []):
            it = state.items.get(item_id)
            if it is None:
                continue
            price = it.properties.get("price")
            if isinstance(price, int) and not isinstance(price, bool) and price >= 0:
                priced.append(it)
        if priced:
            traders_here.append((e, priced))
    if traders_here:
        out.append(
            f"  Trade (1 action/turn): <intent type=\"trade\" "
            f"want=\"<item_id>\" target=\"<npc_id>\"/>"
        )
        for trader, priced_items in traders_here:
            out.append(f"    {trader.entity_id} ({trader.display_name}) sells:")
            for it in priced_items:
                price = it.properties.get("price")
                currency = it.properties.get("currency", "coin")
                out.append(f"      - {it.item_id} ({it.name}) — {price} {currency}")

    # Use item — only list items whose `use` actually applies somewhere
    # in this scene. Items with no `use` property are inert and listing
    # them as "no usable effect" was pure noise. Items with a `use` but
    # no valid target in this room are also suppressed (they'll surface
    # again when the actor moves into a room where they apply).
    #
    # Locks the actor has already unlocked are filtered out of the
    # lockpicking target list — leaving them in invited the LLM into a
    # "pick the lock again" loop in observed runs.
    usable_lines: list[str] = []
    for itm in inventory_items:
        use = itm.properties.get("use")
        if not isinstance(use, str) or not use:
            continue
        valid_targets = _valid_use_item_targets(
            use, view.player_id, other_entities_here, items_here,
            actor_attrs=actor.attributes,
        )
        if valid_targets:
            tgts = ", ".join(valid_targets)
            usable_lines.append(f"    {itm.item_id} ({use}) — valid targets here: {tgts}")
    if usable_lines:
        out.append(
            f"  Use item (1 action/turn): <intent type=\"use_item\" "
            f"item=\"<id>\" target=\"<id>\"/>"
        )
        out.extend(usable_lines)

    # Check — only render when there is a DC-bearing target in scene.
    # Targets the actor has already cleared (locks they've unlocked,
    # puzzles they've solved) are filtered so the LLM does not see
    # them as still-checkable.
    dc_targets = _check_dc_targets(
        view.current_location_id, other_entities_here, items_here, loc,
        actor_attrs=actor.attributes,
    )
    if dc_targets:
        # `_mod` = d20 modifiers (dnd5e_lite); `_pct` = percentile skills
        # (coc_lite). Both are flat int attributes the check intent rolls.
        stat_keys = sorted(
            k for k in actor.attributes.keys()
            if (k.endswith("_mod") or k.endswith("_pct"))
            and isinstance(actor.attributes[k], int)
            and not isinstance(actor.attributes[k], bool)
        )
        out.append(
            f"  Check (1 action/turn): <intent type=\"check\" stat=\"<stat>\" "
            f"target=\"<id>\" purpose=\"<short>\"/>"
        )
        if stat_keys:
            out.append(f"    Stats you have: {', '.join(stat_keys)}")
        out.append(f"    DC-bearing targets here: {', '.join(dc_targets)}")

    # Puzzle answer — only when there's a still-unsolved puzzle target
    # in scene. A puzzle the actor already solved (solved_<id> on actor)
    # is filtered out — observed in M9 runs: Sylvi solved
    # loc_riddle_door once and then re-submitted the same answer 4 more
    # turns in a row because the affordance kept advertising it.
    puzzle_targets: list[str] = []
    if (
        isinstance(loc.attributes.get("puzzle_answer"), str)
        and not _solved_by_party(state, view.current_location_id)
    ):
        puzzle_targets.append(view.current_location_id)
    for itm in items_here:
        if not isinstance(itm.properties.get("puzzle_answer"), str):
            continue
        if _solved_by_party(state, itm.item_id):
            continue
        puzzle_targets.append(itm.item_id)
    if puzzle_targets:
        out.append(
            f"  Puzzle answer (1 action/turn): <intent type=\"puzzle_answer\" "
            f"target=\"<id>\" answer=\"<text>\"/>"
        )
        out.append(f"    Puzzle targets here: {', '.join(puzzle_targets)}")

    # Wait — always present.
    out.append(f"  Wait (skip turn): <intent type=\"wait\"/>")

    out.append("")
    out.append(
        "  Action economy: at most 1 action + 1 move per turn. "
        "Free actions (look, talk) are unlimited. <wait/> consumes the rest."
    )
    return "\n".join(out)


def _valid_use_item_targets(
    use_kind: str,
    actor_id: str,
    entities_in_scene: list,
    items_in_scene: list,
    actor_attrs: dict | None = None,
) -> list[str]:
    """Return the ids in the current scene that are valid targets for an
    item with the given `use` kind. Mirrors the runner's dispatch:
      - heal: any entity in scene (including the actor)
      - lockpicking: items with a `lock_dc` property that the actor
        has NOT already unlocked (an `unlocked_<id>` attribute on the
        actor marks a successful prior pick — skipping it here keeps
        the LLM from re-attempting a lock that is already open).
    Unknown use kinds return [] — the player can still try, but the
    affordance line marks it as no-valid-target.

    Note: `pickup_with_seal` is gone — picking up items is now its own
    PickupIntent rendered separately in the affordances block."""
    attrs = actor_attrs or {}
    if use_kind == "heal":
        return [actor_id] + [e.entity_id for e in entities_in_scene]
    if use_kind == "lockpicking":
        out: list[str] = []
        for i in items_in_scene:
            dc = i.properties.get("lock_dc")
            if not (isinstance(dc, int) and not isinstance(dc, bool)):
                continue
            if attrs.get(f"unlocked_{i.item_id}"):
                continue
            out.append(i.item_id)
        return out
    return []


def _check_dc_targets(
    location_id: str,
    entities_in_scene: list,
    items_in_scene: list,
    location,
    actor_attrs: dict | None = None,
) -> list[str]:
    """Return ids of targets in scene that have any DC-shaped attribute
    or property (lock_dc, search_dc, *_dc, or generic dc). The player
    can target anything for a check, but listing the DC-bearing ones
    prevents the 'check on a non-checkable thing' loop.

    Filters out items whose ONLY DC is `lock_dc` and which the actor
    has already unlocked — the relevant check has been resolved, so
    re-listing the lock invites a repeat-pick loop. Items with
    additional DCs (e.g. search_dc) still surface."""
    attrs = actor_attrs or {}

    def _item_has_unresolved_dc(props: dict, item_id: str) -> bool:
        has_any = False
        has_only_lock = True
        for k, v in props.items():
            if not (k.endswith("_dc") or k == "dc"):
                continue
            if not (isinstance(v, int) and not isinstance(v, bool)):
                continue
            has_any = True
            if k != "lock_dc":
                has_only_lock = False
        if not has_any:
            return False
        if has_only_lock and attrs.get(f"unlocked_{item_id}"):
            return False
        return True

    out: list[str] = []
    for itm in items_in_scene:
        if _item_has_unresolved_dc(itm.properties, itm.item_id):
            out.append(itm.item_id)
    for e in entities_in_scene:
        if _has_dc(e.attributes):
            out.append(e.entity_id)
    if location is not None and _has_dc(location.attributes):
        out.append(location_id)
    return out


def _has_dc(props: dict) -> bool:
    for k, v in props.items():
        if not k.endswith("_dc") and k != "dc":
            continue
        if isinstance(v, int) and not isinstance(v, bool):
            return True
    return False
