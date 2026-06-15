"""
DM agent — M8 narrator + NPC turn planner.

Per the M8 architectural rewrite (m8_build_brief.md):

  - **Players self-declare intents.** The DM is no longer the intent
    classifier. `declare_intent` and `declare_npc_intent` are gone.
  - **NPCs use the same structured-turn protocol.** `plan_npc_turn`
    returns a `PlayerTurnResult` (reused for symmetry — the result
    type is actor-agnostic) containing the NPC's planned intents +
    DM-as-NPC narration prose.
  - **One DMNarration per turn.** `narrate_turn_outcome` takes the
    list of `IntentOutcome` records the runner produced from
    resolving each intent in order, and emits one narration covering
    the whole turn. Saves LLM calls vs per-intent narration.

The DM still owns the M3+M5+M7 locked narration rules (no inventing
numbers / mechanical terms / actions by non-attacker entities). The
narration retry loop is unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import config
from llm import DEFAULT_MODEL, ChatResult, chat as default_chat
from models import WorldState
from player import (
    PlayerAttempt,
    PlayerTurnResult,
    _SUCCESS_STATUSES,
    _classify_player_output,
    _correction_for as _player_correction_for,
    _process_narration,
)
from ruleset import get_action_economy
from tags import (
    IntentTag,
    MalformedTagError,
    Narration,
    extract_narration,
)


ChatFn = Callable[..., ChatResult]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NarrationAttempt:
    chat: ChatResult
    narration: Narration | None
    parse_status: str  # "ok" | "no_tag_found" | "empty_body"
    error_message: str | None


@dataclass(frozen=True)
class NarrationBeatResult:
    """One DMNarration call's result. Carries the retry history for
    measurement; `narration` is None on exhausted-retry failure."""

    chat: ChatResult
    narration: Narration | None
    parse_status: str
    error_message: str | None
    attempts: list[NarrationAttempt] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return self.narration is not None


@dataclass(frozen=True)
class IntentOutcome:
    """One record per intent in a resolved turn. The runner builds these
    after dispatch; the DM consumes them to compose narration.

    `resolved=False` means the intent was skipped (e.g. its target was
    invalidated by a prior intent in the same turn). `summary` is a
    human-readable description of what happened — feeds straight into
    the narration prompt."""

    intent: IntentTag
    resolved: bool
    summary: str


# ---------------------------------------------------------------------------
# DMAgent
# ---------------------------------------------------------------------------


class DMAgent:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        chat_fn: ChatFn | None = None,
        retry_cap: int | None = None,
        ruleset_name: str = "dnd5e_lite",
    ) -> None:
        self.model = model
        self._chat: ChatFn = chat_fn if chat_fn is not None else default_chat
        self.retry_cap = retry_cap if retry_cap is not None else config.RETRY_CAP
        self.ruleset_name = ruleset_name

    # ---- NPC turn planning -------------------------------------------------

    def plan_npc_turn(
        self,
        state: WorldState,
        npc_id: str,
        location_id: str,
        recent_talks: list[tuple[str, str]] | None = None,
    ) -> PlayerTurnResult:
        """
        Plan an NPC's turn. Same protocol as PlayerAgent.act: structured
        intents + narration. Reuses `_classify_player_output` and the
        player retry-correction machinery because the validation rules
        and retry semantics are identical regardless of who's acting.

        `recent_talks` (M9): optional `(speaker_display_name, speech)`
        list of recent talk events targeted at this NPC. The runner
        computes these from the event log and passes them in; the DM
        agent forwards them into the prompt builder.

        Returned PlayerTurnResult — the name is historical (it's used
        for both PC and NPC turn plans).
        """
        base_messages = build_npc_turn_prompt(state, npc_id, location_id, recent_talks)
        messages = base_messages
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
                return PlayerTurnResult(
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

            if attempt_idx == self.retry_cap:
                break

            # One negative example only — see PlayerAgent.act (M12 trim).
            messages = base_messages + [
                {"role": "assistant", "content": chat_result.raw},
                {"role": "user", "content": _player_correction_for(attempt)},
            ]

        last = attempts[-1]
        narration_text, used_fallback, truncated = _process_narration(
            last.raw_narration or ""
        )
        return PlayerTurnResult(
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

    # ---- Turn-outcome narration --------------------------------------------

    def narrate_turn_outcome(
        self,
        actor_id: str,
        outcomes: list[IntentOutcome],
        state: WorldState,
        location_id: str,
        player_text: str | None = None,
    ) -> NarrationBeatResult:
        """
        Produce one DMNarration covering the whole turn's outcomes.
        `player_text` is the actor's prose (PlayerTurnResult.narration_text)
        — included for context so the DM's narration can echo dialog or
        intent. `outcomes` is in resolution order, including SKIPPED
        intents (whose `summary` explains why).
        """
        messages = build_turn_narration_prompt(
            actor_id=actor_id,
            outcomes=outcomes,
            state=state,
            location_id=location_id,
            player_text=player_text,
        )
        return self._run_narration_loop(messages)

    def _run_narration_loop(
        self,
        initial_messages: list[dict[str, str]],
    ) -> NarrationBeatResult:
        """Shared retry/fallback loop. Carries the M3 retry pattern."""
        messages = initial_messages
        attempts: list[NarrationAttempt] = []

        for attempt_idx in range(1 + self.retry_cap):
            chat_result = self._chat(messages, model=self.model)
            attempt = _classify_narration(chat_result)
            attempts.append(attempt)

            if attempt.parse_status == "ok":
                return NarrationBeatResult(
                    chat=chat_result,
                    narration=attempt.narration,
                    parse_status="ok",
                    error_message=None,
                    attempts=attempts,
                )

            if attempt_idx == self.retry_cap:
                break

            # One negative example only — see PlayerAgent.act (M12 trim).
            messages = initial_messages + [
                {"role": "assistant", "content": chat_result.raw},
                {"role": "user", "content": _narration_correction(attempt)},
            ]

        last = attempts[-1]
        return NarrationBeatResult(
            chat=last.chat,
            narration=None,
            parse_status=last.parse_status,
            error_message=last.error_message,
            attempts=attempts,
        )


# ---------------------------------------------------------------------------
# Narration classification (unchanged from M3 + M5)
# ---------------------------------------------------------------------------


def _classify_narration(chat_result: ChatResult) -> NarrationAttempt:
    try:
        narration = extract_narration(chat_result.text)
    except MalformedTagError as e:
        return NarrationAttempt(
            chat=chat_result,
            narration=None,
            parse_status=e.category,
            error_message=str(e),
        )
    return NarrationAttempt(
        chat=chat_result,
        narration=narration,
        parse_status="ok",
        error_message=None,
    )


def _narration_correction(attempt: NarrationAttempt) -> str:
    tag_example = "<narration>your prose here</narration>"

    if attempt.parse_status == "no_tag_found":
        return (
            "Your previous response did not contain a <narration> tag. "
            "Reply with one or two sentences of narrative prose inside a "
            f"{tag_example}, with no other text."
        )
    if attempt.parse_status == "empty_body":
        return (
            "Your previous narration was empty. Reply with one or two "
            "sentences of narrative prose inside a "
            f"{tag_example}, with no other text."
        )
    return (
        f"Your previous response was invalid ({attempt.parse_status}). "
        f"Reply with exactly one {tag_example}, with no other text."
    )


# ---------------------------------------------------------------------------
# Lore helper (kept from M7; used by runner for look/examine outcomes)
# ---------------------------------------------------------------------------


def gather_lore(target_id: str, state: WorldState, include_hidden: bool = False) -> str:
    """Fetch the description / lore text for an inspect/look target.
    `include_hidden` toggles whether `hidden_text` properties surface
    (set by examine, not look). Falls back to the entity/item/location
    name when no richer text is available.

    Strips `[DEMO: ...]` author annotations so the DM's narration prompt
    does not see meta-content."""
    # Local import to avoid a circular import (view_builder imports from
    # projection which is fine, but importing at module top would cycle
    # if anyone ever wires view_builder -> dm).
    from view_builder import strip_demo_annotations

    if target_id in state.locations:
        return strip_demo_annotations(state.locations[target_id].description)
    if target_id in state.items:
        item = state.items[target_id]
        props = item.properties
        parts: list[str] = []
        if isinstance(props.get("text"), str) and props.get("readable"):
            parts.append(strip_demo_annotations(props["text"]))
        elif isinstance(props.get("description"), str):
            parts.append(strip_demo_annotations(props["description"]))
        else:
            parts.append(item.name)
        if include_hidden and isinstance(props.get("hidden_text"), str):
            parts.append(f"(Hidden detail: {strip_demo_annotations(props['hidden_text'])})")
        return " ".join(parts) if parts else item.name
    if target_id in state.entities:
        entity = state.entities[target_id]
        attrs = entity.attributes
        bits = [entity.display_name, f"({entity.kind})"]
        if "hp" in attrs and "max_hp" in attrs:
            bits.append(f"hp {attrs['hp']}/{attrs['max_hp']}")
        if "status" in attrs:
            bits.append(f"status: {attrs['status']}")
        return " ".join(bits)
    return target_id  # unknown — defensive


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------


_NARRATION_SYSTEM = (
    "You are the Dungeon Master. The mechanical resolution has already "
    "happened. Your job in this beat is to narrate the outcome in 1-3 "
    "sentences. You must not invent any number, hit, miss, or outcome that "
    "is not stated in the outcomes provided. Do not use the mechanical "
    "terms \"critical\", \"crit\", \"critical hit\", \"advantage\", "
    "\"disadvantage\", \"saving throw\", \"save\", or \"fumble\" unless "
    "those exact words appear in the outcomes. Describe the events with "
    "prose; do not introduce any game mechanic the outcomes did not name. "
    "Do not describe actions taken by entities other than the acting "
    "actor in this turn — other combatants will have their own turns.\n\n"
    "DO NOT ECHO THE ACTOR (CRITICAL): The player has already narrated "
    "what their character does and says in their own prose for this turn. "
    "Your narration must NOT repeat, paraphrase, restate, or quote that "
    "prose back. Your role is to narrate the WORLD'S RESPONSE — the "
    "environment, the result of dice, and what becomes revealed — never "
    "to retell the actor's own actions. If the "
    "actor's prose already covered the moment fully (e.g. a simple move "
    "to an empty room) and the outcomes add nothing, keep your beat to a "
    "single short environmental sentence (what the new room looks like, "
    "what the actor now sees) rather than re-describing the actor.\n\n"
    "DO NOT INVENT ENTITIES (CRITICAL): Refer only to characters, items, "
    "features, and lore that are named in the outcomes, the location/"
    "entity/item names supplied above, or read aloud from a `readable` "
    "item's `text`. Do NOT add objects (keys, parchments, glowing runes, "
    "etc.) that the outcomes do not list. If a container is opened and "
    "no contents are listed in the outcome, the container was empty — "
    "do not invent loot. If a target's lore is just its name, describe "
    "only its outward appearance; do not fabricate inner details.\n\n"
    "ACTION VOCABULARY IS LITERAL (CRITICAL): The outcomes name the "
    "exact action that resolved. `examined X` means the actor looked at "
    "X carefully — they did NOT take it, lift it, grab it, or hold it. "
    "`looked at X` means the actor's eyes passed over X — same rule. "
    "Only when the outcome literally contains `picked up` may you "
    "describe the actor as holding, lifting, taking, grabbing, "
    "pocketing, or carrying the item. Only when the outcome contains "
    "`opened` may you describe contents being revealed. Only when the "
    "outcome contains `moved from X to Y` may you describe the actor "
    "as in the new room — and even then, do not narrate them taking "
    "anything from that room unless a pickup outcome also fired this "
    "turn. A singular world-object does not duplicate: if another PC "
    "has already picked it up in a prior turn, it is GONE from where "
    "it lay — do not narrate a second PC lifting a phantom copy. "
    "Never introduce objects, rooms, or creatures the scene state does "
    "not list.\n\n"
    "ACTOR NAMES: Treat each character's display_name as a single name. "
    "A surname like \"Ironhide\" is part of the character's name, NOT a "
    "piece of armor or equipment. Do not split names into objects and "
    "do not narrate damage as being done to a character's armor when the "
    "outcome says hp.\n\n"
    "SKIPPED outcomes (CRITICAL): When an outcome is marked [SKIPPED], "
    "that action DID NOT HAPPEN mechanically. Your narration MUST convey "
    "failure or no-effect for it — never success, never partial success, "
    "never ambiguous 'with quiet persistence'-style prose that could be "
    "read as working. State clearly that the attempt produced nothing, "
    "and where the outcome supplies a reason (e.g. 'no lock_dc', 'not in "
    "scene', 'wrong answer'), reflect that reason in plain language so "
    "the player understands what to try differently. The mechanical "
    "engine has already decided the action did not succeed; you only "
    "describe that failure honestly."
)


_NPC_TURN_SYSTEM = (
    "You are the Dungeon Master. It is now an NPC's turn — you plan its "
    "action(s). The NPC is a character in the world; act as it would. "
    "Emit a structured turn: zero or more <intent> tags describing what "
    "the NPC does, followed by exactly one <narration> tag with the NPC's "
    "prose (what it does and says in 1-2 sentences). Use only ids in the "
    "NPC's affordances list. Action economy: at most 1 action + 1 move "
    "per turn; free actions (look, talk) unlimited. Do not invent dice "
    "or game mechanics.\n\n"
    "Stay in character — your behavior is governed by your disposition "
    "and persona, listed below. If you have a `secret`, the players must "
    "work to discover it via conversation; do not volunteer it. Reveal "
    "it only if they specifically press on inconsistencies or offer a "
    "meaningful trade. If your `negotiation_levers` describe specific "
    "conditions for cooperation, those are the levers the players must "
    "hit before you'll agree."
)


def build_turn_narration_prompt(
    actor_id: str,
    outcomes: list[IntentOutcome],
    state: WorldState,
    location_id: str,
    player_text: str | None = None,
) -> list[dict[str, str]]:
    """The DM narration prompt. Lists outcomes in resolution order; the
    DM weaves them into one prose beat."""
    actor = state.entities.get(actor_id)
    actor_name = actor.display_name if actor else actor_id
    is_npc = actor is not None and actor.kind == "npc"
    location = state.locations.get(location_id)
    location_name = location.name if location else location_id

    lines = [
        f"Actor: {actor_name} (id: {actor_id})",
        f"Location: {location_name} (id: {location_id})",
    ]
    # For an NPC turn the actor has NO committed prose of their own (NPCs don't
    # emit a PlayerAction), so the DM must voice them — surface their persona so
    # the spoken line lands in character.
    if is_npc:
        persona = actor.attributes.get("persona", "")
        if isinstance(persona, str) and persona.strip():
            lines.append(f"{actor_name}'s persona: {persona.strip()}")
    # `player_text` is intentionally NOT surfaced to the DM prompt. The
    # actor's prose has already been committed as a PlayerAction visible
    # to the players; the DM's job is to narrate the world's response,
    # not to restate the actor. Including the prose here caused the DM
    # to paraphrase it back almost verbatim every turn.
    _ = player_text

    # Ground the DM on where every objective item currently is. Without
    # this the model has hallucinated wrong locations for the campaign
    # macguffin — e.g. narrating "the Heartstone embedded in the
    # Warden's chest" on turns when it's still on its pedestal in the
    # inner vault. Surfacing the authoritative current location makes
    # those inventions land as flat contradictions of state the DM was
    # just told.
    objective_lines = _render_objective_items(state)
    if objective_lines:
        lines.append("")
        lines.extend(objective_lines)

    lines.append("")
    lines.append("Resolved outcomes (in order):")
    for idx, outcome in enumerate(outcomes, start=1):
        status = "" if outcome.resolved else " [SKIPPED]"
        lines.append(f"  {idx}. <{outcome.intent.type}>{status}: {outcome.summary}")

    if not outcomes:
        lines.append("  (none — actor took no mechanical actions this turn)")

    lines.append("")
    if is_npc:
        # NPC turn: the DM IS this NPC's voice — nothing else narrates them.
        lines.append(
            f"You are voicing {actor_name}, an NPC taking THEIR OWN turn. "
            f"{actor_name} is the subject of this beat — narrate what THEY do, "
            f"and when they speak, give their actual spoken line in double "
            f"quotes, in character with the persona above. Use the resolved "
            f"outcomes (a talk outcome contains the words they said). If they "
            f"took no mechanical action, still have {actor_name} react or speak "
            f"in character to the party. 1-3 sentences. Do NOT narrate the "
            f"players' own actions. Treat any key objective item's listed "
            f"location as fact. Advance the exchange — do not re-explain a "
            f"warning, direction, or offer you have likely already given; say "
            f"something new or move it forward."
        )
    else:
        # The don't-retell-the-actor and don't-invent rules live in
        # _NARRATION_SYSTEM (the CRITICAL blocks) — not restated here. This
        # block carries only the per-turn additions: the beat shape, the
        # NPC-no-speak rule, and the objective-item grounding.
        lines.append(
            "Narrate this turn as a single beat in 1-3 sentences — the "
            "world's response to the actor only (environment, mechanical "
            "results, what becomes visible). Do NOT speak or act for "
            "any NPC: a present NPC takes its OWN turn and will respond then — "
            "at most a wordless reaction (a glance, a tensed hand), never a "
            "spoken line. If a key objective item is listed above, treat its "
            "location as fact — do not describe it as being anywhere else "
            "(embedded in an NPC, elsewhere in the room, etc.)."
        )
    lines.append("")
    lines.append(
        "Reply with EXACTLY ONE tag, on its own line:\n"
        "  <narration>your prose here</narration>"
    )
    user = "\n".join(lines)
    return [
        {"role": "system", "content": _NARRATION_SYSTEM},
        {"role": "user", "content": user},
    ]


def _render_objective_items(state: WorldState) -> list[str]:
    """Build the "[Key objective items]" grounding block for the DM
    narration prompt. Each item the seed flags with `type: objective`
    is reported with its current location — either the room id it sits
    in, or the entity id that is carrying it (post-pickup). Returns an
    empty list when the world has no objective items so a campaign
    without one pays no prompt cost."""
    objective_items = [
        item for item in state.items.values()
        if item.properties.get("type") == "objective"
    ]
    if not objective_items:
        return []
    lines = [
        "[Key objective items — authoritative current state]",
        "These items' locations below are the ground truth. Do not narrate "
        "them as being anywhere else.",
    ]
    for item in objective_items:
        where: str
        if item.location_id is not None:
            loc = state.locations.get(item.location_id)
            loc_name = loc.name if loc is not None else item.location_id
            where = f"in {loc_name} (id: {item.location_id})"
        else:
            holder = next(
                (e for e in state.entities.values() if item.item_id in e.inventory),
                None,
            )
            if holder is not None:
                where = f"carried by {holder.display_name} (id: {holder.entity_id})"
            else:
                where = "location unknown"
        lines.append(f"  - {item.name} (id: {item.item_id}): {where}")
    return lines


def build_npc_turn_prompt(
    state: WorldState,
    npc_id: str,
    location_id: str,
    recent_talks: list[tuple[str, str]] | None = None,
) -> list[dict[str, str]]:
    """The DM-as-NPC prompt. Renders an NPC-perspective view of the scene
    (entities present, location, etc.) and asks for a structured turn.

    M9: `recent_talks` is an optional list of `(speaker_name, speech)`
    tuples — recent things players have said to this NPC. The agent
    layer (which has access to the event log) can pass these in; the
    pure prompt builder does not walk the log itself.
    """
    location = state.locations.get(location_id)
    npc = state.entities.get(npc_id)
    if npc is None or location is None:
        raise ValueError(
            f"plan_npc_turn: missing entity {npc_id!r} or location {location_id!r}"
        )

    npc_hp = npc.attributes.get("hp", "?")
    npc_max_hp = npc.attributes.get("max_hp", "?")
    npc_status = npc.attributes.get("status", "")

    # M9: surface persona/disposition/negotiation_levers/secret/goals
    # from the NPC's seed attributes. Each one is optional — missing
    # fields are omitted. This is the entire prompt-driven NPC behavior;
    # no per-NPC code branches.
    #
    # B2 addition: `goals` (list[str]) is the per-NPC analogue of the
    # PARTY_GOALS that PlayerAgent surfaces — it gives the NPC LLM a
    # consistent pull across turns instead of pure scene-reaction. For
    # hostile NPCs goals are simple ("defend this hall, attack
    # intruders"). For conversational NPCs they can be nuanced or
    # deliberately deceptive ("get freed by claiming to know the path,
    # even though you do not"). Goals + secret + persona compose: a
    # deceptive goal references the secret as the lie's target.
    persona = npc.attributes.get("persona")
    disposition = npc.attributes.get("disposition")
    levers = npc.attributes.get("negotiation_levers")
    secret = npc.attributes.get("secret")
    goals_raw = npc.attributes.get("goals")
    role_lines: list[str] = []
    if isinstance(persona, str) and persona:
        role_lines.append(f"  Persona: {persona}")
    if isinstance(disposition, str) and disposition:
        role_lines.append(f"  Disposition: {disposition}")
    if isinstance(levers, str) and levers:
        role_lines.append(f"  Negotiation levers (what would move you): {levers}")
    if isinstance(secret, str) and secret:
        role_lines.append(
            f"  Private knowledge (do NOT volunteer; only reveal under pressure or trade): {secret}"
        )
    if isinstance(goals_raw, list) and goals_raw:
        role_lines.append("  Your goals (what you are trying to accomplish):")
        for g in goals_raw:
            if isinstance(g, str) and g:
                role_lines.append(f"    - {g}")
    role_block = "\n".join(role_lines) if role_lines else ""

    talk_block = ""
    if recent_talks:
        talk_lines = ["[Recent things others have said to you]"]
        for speaker, speech in recent_talks[-5:]:
            talk_lines.append(f"  {speaker}: \"{speech}\"")
        talk_block = "\n".join(talk_lines)

    # Other entities in this location (potential targets / conversation partners).
    others = [
        e for e in state.entities.values()
        if e.location_id == location_id and e.entity_id != npc_id
    ]
    # Categorize for the affordances hint
    hostile_pcs = [e for e in others if e.kind == "pc"]  # NPCs typically target PCs
    other_npcs = [e for e in others if e.kind == "npc"]

    other_lines: list[str] = []
    for e in others:
        attrs = e.attributes
        hp = attrs.get("hp", "?")
        max_hp = attrs.get("max_hp", "?")
        bit = f"  - {e.display_name} ({e.kind}, id: {e.entity_id}) — hp {hp}/{max_hp}"
        if attrs.get("status"):
            bit += f", status: {attrs['status']}"
        other_lines.append(bit)
    others_block = "\n".join(other_lines) if other_lines else "  (no one else here)"

    move_csv = ", ".join(sorted(location.connections)) if location.connections else "(no connections)"
    attack_csv = ", ".join(e.entity_id for e in hostile_pcs) if hostile_pcs else "(no PC targets here)"
    talk_csv = ", ".join(e.entity_id for e in others) if others else "(no one to talk to)"

    role_section = (f"\n[Your character]\n{role_block}\n" if role_block else "")
    talk_section = (f"\n{talk_block}\n" if talk_block else "")

    user = (
        f"It is {npc.display_name}'s turn.\n"
        f"Location: {location.name} (id: {location_id})\n"
        f"{npc.display_name} (id: {npc_id}, npc, hp {npc_hp}/{npc_max_hp}"
        f"{', status: ' + npc_status if npc_status else ''})\n"
        f"{role_section}"
        f"\nOthers present in this location:\n{others_block}\n"
        f"{talk_section}"
        f"\n[Affordances — what this NPC can do this turn]\n"
        f"  Move (1/turn): <intent type=\"move\" target=\"<id>\"/>\n"
        f"    Connected: {move_csv}\n"
        f"  Attack (1 action/turn): <intent type=\"attack\" target=\"<id>\"/>\n"
        f"    Available targets: {attack_csv}\n"
        f"  Talk (free): <intent type=\"talk\" target=\"<id>\">speech</intent>\n"
        f"    Available targets: {talk_csv}\n"
        f"  Look (free, unlimited): <intent type=\"look\" target=\"<id>\"/>\n"
        f"  Examine (1 action/turn): <intent type=\"examine\" target=\"<id>\"/>\n"
        f"  Wait (skip turn): <intent type=\"wait\"/>\n\n"
        f"Reply with intent tag(s) followed by exactly one <narration> tag "
        f"with the NPC's prose."
    )
    return [
        {"role": "system", "content": _NPC_TURN_SYSTEM},
        {"role": "user", "content": user},
    ]
