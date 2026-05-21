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

from dataclasses import dataclass, field

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


class ViewBuilderError(ValueError):
    """Raised when the player doesn't appear in the event log."""


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

    return PlayerView(
        player_id=player_id,
        current_location_id=player_loc,
        visible_events=visible,
        summary=summary,
        visited_locations=visited_locations,
        consecutive_turns_here=consecutive_turns_here,
        nearby_commotion=nearby_commotion,
    )


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


def render_for_prompt(view: PlayerView, state: WorldState) -> str:
    """
    Format `view` into a prose block suitable for the player's LLM prompt.

    `state` supplies the names/descriptions of locations + entities (the
    view only carries event references; render time is when we look up
    human-readable details). This split keeps the structural test (on
    `visible_events`) decoupled from text formatting.
    """
    lines: list[str] = []

    if view.summary is not None:
        lines.append("[Story so far]")
        lines.append(view.summary.text)
        lines.append("")

    location = state.locations.get(view.current_location_id)
    if location is not None:
        lines.append(f"[You are in {location.name}.]")
        lines.append(location.description)
    else:
        lines.append(f"[You are in {view.current_location_id}.]")

    me = state.entities.get(view.player_id)
    others_present = [
        e for e in state.entities.values()
        if e.location_id == view.current_location_id and e.entity_id != view.player_id
    ]
    if others_present:
        lines.append("")
        lines.append("Present with you:")
        for e in others_present:
            status = e.attributes.get("status")
            tag = f" ({status})" if status and status != "hostile" else ""
            lines.append(f"  - {e.display_name}{tag}")

    if view.visible_events:
        lines.append("")
        lines.append("[Recent events]")
        for event in view.visible_events:
            p = event.payload
            if isinstance(p, PlayerAction):
                speaker = state.entities.get(p.player_id)
                name = speaker.display_name if speaker else p.player_id
                lines.append(f'{name}: "{p.text}"')
            elif isinstance(p, DMNarration):
                lines.append(f"DM: {p.text}")
            # SummaryCreated already rendered at the top; do not repeat.

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

    # M8.1: spatial memory — surface every visited location + its
    # connections so the player has a discovered-map view of the
    # dungeon instead of having to reconstruct geography each turn
    # from prose.
    visited_block = _render_visited_rooms(view, state)
    if visited_block:
        lines.append("")
        lines.append(visited_block)

    # M8: append the affordances block so the player prompt can list
    # exactly which ids are valid for each intent type. Without this,
    # the model has to infer affordances from the scene description —
    # which is the M7-demo bias toward `inspect`.
    affordances = _render_affordances(view, state)
    if affordances:
        lines.append("")
        lines.append(affordances)

    return "\n".join(lines)


def _render_visited_rooms(view: PlayerView, state: WorldState) -> str:
    """M8.1 spatial-memory block: each room the player has visited, with
    its connections. The current room is marked. Rooms the player has
    never visited do NOT appear (M4 G1 carries — visited_locations was
    built from this player's own create+move events only).

    B2 follow-up: each exit is annotated as [visited] or [unexplored]
    based on whether the exit id is in the player's visited_locations
    set. After the per-room map, a [Frontier] section lists every
    unique unvisited exit id reachable in one step from any visited
    room. Names of unvisited rooms are NOT surfaced (preserves TTRPG
    fog-of-war: PCs don't know what's behind a door until they open
    it)."""
    if not view.visited_locations:
        return ""
    visited_set: set[str] = set(view.visited_locations)
    lines = ["[Rooms you have explored — your discovered map]"]
    frontier_seen: set[str] = set()
    for loc_id in view.visited_locations:
        loc = state.locations.get(loc_id)
        if loc is None:
            continue
        marker = "  ← you are here" if loc_id == view.current_location_id else ""
        lines.append(f"  {loc_id} — {loc.name}{marker}")
        if not loc.connections:
            lines.append("    Exits: (no exits)")
            continue
        lines.append("    Exits:")
        for exit_id in sorted(loc.connections):
            tag = "[visited]" if exit_id in visited_set else "[unexplored]"
            lines.append(f"      - {exit_id} {tag}")
            if exit_id not in visited_set:
                frontier_seen.add(exit_id)

    if frontier_seen:
        lines.append("")
        lines.append("[Frontier — unexplored rooms one step from your map]")
        lines.append(
            "These rooms connect to a room you have been in but you have "
            "not entered them yet. Their contents are unknown until you "
            "move into them."
        )
        # Sort for deterministic output (test-friendly + replay-stable).
        for exit_id in sorted(frontier_seen):
            # Show which visited room(s) reach this frontier id; helps the
            # LLM plan a route.
            from_rooms = sorted(
                v for v in view.visited_locations
                if exit_id in (state.locations[v].connections if v in state.locations else [])
            )
            from_csv = ", ".join(from_rooms)
            lines.append(f"  - {exit_id} (reachable from: {from_csv})")
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

    # Move
    if loc.connections:
        conns = ", ".join(sorted(loc.connections))
        out.append(f"  Move (1/turn): <intent type=\"move\" target=\"<id>\"/>")
        out.append(f"    Connected: {conns}")
    else:
        out.append(f"  Move: (no connections from here)")

    # Look — list everything visible: room, items here, items carried, entities here
    look_ids: list[str] = [view.current_location_id]
    look_ids += [e.entity_id for e in other_entities_here]
    look_ids += [i.item_id for i in items_here]
    look_ids += [i.item_id for i in inventory_items]
    look_csv = ", ".join(look_ids) if look_ids else "(nothing in particular)"
    out.append(f"  Look (free, unlimited): <intent type=\"look\" target=\"<id>\"/>")
    out.append(f"    Visible: {look_csv}")

    # Examine — same id space as look, but it's an action (uses your slot)
    out.append(f"  Examine (1 action/turn): <intent type=\"examine\" target=\"<id>\"/>")
    out.append(f"    (Same ids as look; examine is careful inspection — may reveal hidden details.)")

    # Attack — hostiles only (suggestion). Always show the tag form so
    # the model has the syntax in front of it even when no hostiles are
    # present (consistency across turns matters more than terseness).
    out.append(f"  Attack (1 action/turn): <intent type=\"attack\" target=\"<id>\"/>")
    if hostile_entities:
        atk_csv = ", ".join(e.entity_id for e in hostile_entities)
        out.append(f"    Hostile targets here: {atk_csv}")
    else:
        out.append(f"    (no hostile targets present)")

    # Talk — non-hostiles (suggestion). Same: always show syntax.
    out.append(f"  Talk (free): <intent type=\"talk\" target=\"<id>\">speech</intent>")
    if non_hostile_entities:
        talk_csv = ", ".join(e.entity_id for e in non_hostile_entities)
        out.append(f"    Present (non-hostile): {talk_csv}")
    else:
        out.append(f"    (no one to speak with here)")

    # M9 follow-up: Pickup — items in this room that can be added to
    # inventory. Containers and locks are filtered out (see
    # runner._NON_PICKUPABLE_TYPES); everything else is implicitly
    # takeable.
    out.append(
        f"  Pickup (1 action/turn): <intent type=\"pickup\" target=\"<item_id>\"/>"
    )
    pickupable: list[str] = []
    for itm in items_here:
        if itm.item_id in (actor.inventory or []):
            continue
        item_type = itm.properties.get("type")
        if isinstance(item_type, str) and item_type in {"container", "lock", "fixture"}:
            continue
        pickupable.append(itm.item_id)
    if pickupable:
        out.append(f"    Items here you can pick up: {', '.join(pickupable)}")
    else:
        out.append(f"    (no loose items in this room)")

    # M9 follow-up: Give — atomic one-way transfer to another entity in
    # the same room. Lists inventory items + present entities so the LLM
    # has the (item, target) tuple in front of it.
    out.append(
        f"  Give (1 action/turn): <intent type=\"give\" item=\"<item_id>\" target=\"<entity_id>\"/>"
    )
    if inventory_items and other_entities_here:
        inv_csv = ", ".join(i.item_id for i in inventory_items)
        tgt_csv = ", ".join(e.entity_id for e in other_entities_here)
        out.append(f"    Your items: {inv_csv}")
        out.append(f"    Recipients here: {tgt_csv}")
    elif not inventory_items:
        out.append(f"    (no items in your inventory to give)")
    else:
        out.append(f"    (no one here to give items to)")

    # M9 follow-up: Open — containers in this room. Locked containers
    # show their lock status; the affordance hint reminds the LLM to
    # pick the lock first.
    containers_here = [
        i for i in items_here
        if i.properties.get("type") == "container"
    ]
    out.append(
        f"  Open (1 action/turn): <intent type=\"open\" target=\"<container_id>\"/>"
    )
    if containers_here:
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
    else:
        out.append(f"    (no containers in this room)")

    # M9 follow-up: Trade — buy a priced item from a merchant. A
    # merchant is any NPC in scene who carries at least one item with a
    # `price` property. Trades pay the listed price out of the actor's
    # currency attribute (default "coin"); no haggling at the
    # structural level (NPCs may negotiate in prose).
    out.append(
        f"  Trade (1 action/turn): <intent type=\"trade\" "
        f"want=\"<item_id>\" target=\"<npc_id>\"/>"
    )
    traders_here: list[tuple] = []  # (npc, list_of_priced_items)
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
        for trader, priced_items in traders_here:
            out.append(f"    {trader.entity_id} ({trader.display_name}) sells:")
            for it in priced_items:
                price = it.properties.get("price")
                currency = it.properties.get("currency", "coin")
                out.append(f"      - {it.item_id} ({it.name}) — {price} {currency}")
    else:
        out.append(f"    (no merchants here)")

    # M9: Use item — for each inventory item with a `use` property,
    # surface the set of VALID targets in the current scene. If no valid
    # targets exist for an item's use kind, say so explicitly. This
    # prevents the player LLM from trying lockpicks on a non-lockable
    # object turn after turn.
    out.append(
        f"  Use item (1 action/turn): <intent type=\"use_item\" item=\"<id>\" target=\"<id>\"/>"
    )
    if inventory_items:
        for itm in inventory_items:
            use = itm.properties.get("use")
            if not isinstance(use, str) or not use:
                out.append(f"    {itm.item_id} (no usable effect)")
                continue
            valid_targets = _valid_use_item_targets(
                use, view.player_id, other_entities_here, items_here,
            )
            if valid_targets:
                tgts = ", ".join(valid_targets)
                out.append(f"    {itm.item_id} ({use}) — valid targets here: {tgts}")
            else:
                out.append(
                    f"    {itm.item_id} ({use}) — NO valid target in this scene "
                    f"(move to a room where {use!r} applies)"
                )
    else:
        out.append(f"    (no items in inventory)")

    # M9: Check — surface DC-bearing targets specifically. The LLM can
    # still attempt a check on any id, but it'll SKIP if no DC; listing
    # known DC-bearing targets prevents the dead-end loop.
    stat_keys = sorted(
        k for k in actor.attributes.keys()
        if k.endswith("_mod") and isinstance(actor.attributes[k], int)
        and not isinstance(actor.attributes[k], bool)
    )
    out.append(
        f"  Check (1 action/turn): <intent type=\"check\" stat=\"<stat>\" "
        f"target=\"<id>\" purpose=\"<short>\"/>"
    )
    if stat_keys:
        out.append(f"    Stats you have: {', '.join(stat_keys)}")
    dc_targets = _check_dc_targets(view.current_location_id, other_entities_here, items_here, loc)
    if dc_targets:
        out.append(f"    DC-bearing targets here: {', '.join(dc_targets)}")
    else:
        out.append(
            f"    (no targets in this room have an authored DC — "
            f"a check here will fail with 'no DC')"
        )

    # M9: Puzzle answer — only surface targets that actually carry a
    # puzzle_answer. If none, just show the syntax (puzzles may exist
    # elsewhere in the dungeon).
    puzzle_targets: list[str] = []
    if isinstance(loc.attributes.get("puzzle_answer"), str):
        puzzle_targets.append(view.current_location_id)
    for itm in items_here:
        if isinstance(itm.properties.get("puzzle_answer"), str):
            puzzle_targets.append(itm.item_id)
    out.append(
        f"  Puzzle answer (1 action/turn): <intent type=\"puzzle_answer\" "
        f"target=\"<id>\" answer=\"<text>\"/>"
    )
    if puzzle_targets:
        out.append(f"    Puzzle targets here: {', '.join(puzzle_targets)}")
    else:
        out.append(f"    (no puzzle targets here)")

    # Wait
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
) -> list[str]:
    """Return the ids in the current scene that are valid targets for an
    item with the given `use` kind. Mirrors the runner's dispatch:
      - heal: any entity in scene (including the actor)
      - lockpicking: items with a `lock_dc` property
    Unknown use kinds return [] — the player can still try, but the
    affordance line marks it as no-valid-target.

    Note: `pickup_with_seal` is gone — picking up items is now its own
    PickupIntent rendered separately in the affordances block."""
    if use_kind == "heal":
        return [actor_id] + [e.entity_id for e in entities_in_scene]
    if use_kind == "lockpicking":
        return [
            i.item_id for i in items_in_scene
            if isinstance(i.properties.get("lock_dc"), int)
            and not isinstance(i.properties.get("lock_dc"), bool)
        ]
    return []


def _check_dc_targets(
    location_id: str,
    entities_in_scene: list,
    items_in_scene: list,
    location,
) -> list[str]:
    """Return ids of targets in scene that have any DC-shaped attribute
    or property (lock_dc, search_dc, *_dc, or generic dc). The player
    can target anything for a check, but listing the DC-bearing ones
    prevents the 'check on a non-checkable thing' loop."""
    out: list[str] = []
    for itm in items_in_scene:
        if _has_dc(itm.properties):
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
