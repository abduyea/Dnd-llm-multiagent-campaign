# TTRPG LLM Engine — V2

A turn-based tabletop RPG engine where local LLMs play the player characters
and the Dungeon Master. PCs propose structured actions; an event-sourced
runner resolves them against game rules; the DM narrates outcomes. The
engine's contract is "LLM proposes, runner disposes" — the model never
mutates state directly.

The included demo (`m9_demo.py`) runs a two-PC party through a 15-room
dungeon and finishes with a scenario-coverage gate report.

---

## Prerequisites

- Python 3.10 or later
- [Ollama](https://ollama.com) installed and running locally
- A capable instruction-following local model (defaults to `qwen3:14b`,
  override with `--model`)

Python dependencies:

```bash
pip install -r requirements.txt
```

---

## Running the demo

```bash
# 1. Start the Ollama server (in a separate terminal)
ollama serve

# 2. Pull the default model (one-time)
ollama pull qwen3:14b

# 3. Run the demo
python m9_demo.py
```

Per-run artifacts land in `runs/m9_<timestamp>/`:

- `events.jsonl` — the canonical event log for the run
- `measurements.json` — one record per LLM call (latency, prompt size,
  parse status)
- `debug.jsonl` — fallback records when the retry loop is exhausted

CLI options:

| Flag | Default | Purpose |
|---|---|---|
| `--max-turns N` | 40 | Hard cap on scheduler ticks |
| `--seed N` | random | RNG seed for reproducible dice |
| `--model NAME` | `qwen3:14b` | Override the LLM model |
| `--retry-cap N` | 3 | Retries on malformed LLM output |
| `--skip-ollama-check` | off | Bypass the startup model-availability check |

The demo ends with a six-criterion gate report. A passing run hits ≥5/6.

---

## Architecture

The engine is layered. Lower layers do not depend on higher ones; each
file has a single responsibility.

### Spine — event-sourced game state

| File | What it does |
|---|---|
| **`models.py`** | Pydantic dataclasses for the closed payload vocabulary (`PlayerAction`, `DMNarration`, `EntityMoved`, `AttributeSet`, `AttributeDelta`, `InventoryAdded`, `InventoryRemoved`, `DiceRolled`, `CombatStart`, `CombatEnd`, `SummaryCreated`, `EntityCreated`, `ItemCreated`, `LocationCreated`), plus `WorldState`, `Entity`, `Item`, `Location`, `Event`, `EventCause`. State changes happen ONLY through these payloads. |
| **`eventlog.py`** | Append-only JSONL log. The single source of truth. |
| **`projection.py`** | Pure function `project(events) → WorldState`. Replays the log to reconstruct current state — same events in, same state out. |
| **`seed.py`** | Loads a dungeon JSON into the log as the initial `LocationCreated` / `EntityCreated` / `ItemCreated` events. |

### Mechanics — game rules

| File | What it does |
|---|---|
| **`dice.py`** | Formula parser and roller (`1d20+5`, `2d4+2`). Pure given an RNG. |
| **`mechanics.py`** | Resolves combat attacks (to-hit + damage) and skill checks (1d20 + stat_mod vs DC). Returns resolution data + the payloads to stage. |
| **`ruleset.py`** | Action economy validator (`dnd5e_lite`: at most 1 action + 1 move per turn; unlimited free actions like look/talk). |

### Tag protocol — structured LLM I/O

| File | What it does |
|---|---|
| **`tags.py`** | Pydantic intent classes (`AttackIntent`, `MoveIntent`, `LookIntent`, `ExamineIntent`, `TalkIntent`, `WaitIntent`, `CheckIntent`, `UseItemIntent`, `PuzzleAnswerIntent`, `PickupIntent`, `GiveIntent`, `OpenIntent`, `TradeIntent`) plus regex extractors for `<intent ... />` and `<narration>...</narration>` in LLM output. Players and NPCs both emit intents through these tags. Malformed output triggers retries. |

### Agents — LLM wrappers

| File | What it does |
|---|---|
| **`llm.py`** | Thin Ollama wrapper. `ChatResult` captures latency, prompt size, and completion size for measurement. |
| **`player.py`** | `PlayerAgent`: produces a turn plan (intents + prose narration). Tracks party-level mission goals, consecutive empty-intent turns (forward-progress escalation), and salvages narration prose from truncated/malformed output. |
| **`dm.py`** | `DMAgent`: narrates per-turn outcomes via `narrate_turn_outcome`, plays NPC turns via `plan_npc_turn`. NPCs use the same structured-turn protocol as PCs — their behavior is shaped by `persona` / `disposition` / `goals` / `negotiation_levers` / `secret` surfaced from the seed into the prompt. |

### Orchestration

| File | What it does |
|---|---|
| **`runner.py`** | `run_turn` (PC) and `run_npc_turn` (NPC). Walks the validated intent plan, dispatches per-intent resolvers, stages payloads through a `TurnBuffer` (atomic commit/discard with the DM's narration). Auto-emits `CombatStart` + initiative when an attack lands on a hostile; auto-emits `CombatEnd` on disengage or full neutralization. End-of-turn ticks countdown attributes. |
| **`scheduler.py`** | Pure function over the log; decides whose turn is next. Two modes: **exploration** (PCs rotate, with NPCs interleaved on talk / give / hostile-on-entry triggers) and **combat** (initiative-ordered, one turn per round per participant). Replay-stable. |

### View scoping

| File | What it does |
|---|---|
| **`view_builder.py`** | `build_view(events, player_id) → PlayerView`. Per-player visibility filter (each PC sees events only from their own location plus global summaries). `render_for_prompt` produces the LLM-facing scene render: current room, recent events, status (HP + currency), discovered-map block with visited/unexplored exit markers, frontier section, affordances per intent type, and nearby-combat sound cues for adjacent rooms. |

### Infrastructure

| File | What it does |
|---|---|
| **`config.py`** | Single tuning point for retry caps, char budgets, thresholds (empty-intent escalation, room stickiness, disengage window, NPC scheduling marker name, etc.). |
| **`debug_log.py`** | Fallback record writer when the retry loop exhausts. |
| **`summarizer.py`** | Between-turn summarization; fires when the next prompt would exceed `PROMPT_CHAR_BUDGET`. Emits `SummaryCreated` events that survive log replay (per invariant 7: summaries are advisory, never affect projection). |
| **`m2_inspect.py`** | `MeasurementSink` — writes one record per LLM call (latency + parse stats) to `measurements.json`. |

### Content

| File | What it is |
|---|---|
| **`demo_dungeon.json`** | The demo seed: 15 rooms, 2 PCs (Brakka the fighter, Sylvi the rogue), 6 NPCs (skeletons, Aldous the deceptive prisoner, Hessa the merchant, the Bound Warden, the Echo Gallery Lurker), 20 items. The goal: reach the Heart Vault, retrieve the Heartstone before the 5-turn seal countdown closes, escape. |
| **`m9_demo.py`** | Demo entry point. Loads the seed, instantiates `PlayerAgent`s with party goals, loops through scheduler-selected turns until either the turn cap is hit or all PCs are neutralized. Writes per-run artifacts and prints a gate report at the end. |

---

## The turn loop (high-level)

For each tick:

1. **Scheduler** reads the log and picks the next actor (a PC by
   rotation, or an NPC if one is queued via a pending-response marker,
   or an initiative-ordered combatant during combat).
2. **View builder** computes that actor's scoped view of the world.
3. The actor's agent (PlayerAgent for PCs, `DMAgent.plan_npc_turn` for
   NPCs) produces a structured turn plan: one or more `<intent>` tags
   plus a `<narration>` prose block.
4. **Runner** walks the plan, dispatching each intent to its resolver
   against a turn buffer (so intra-turn intents see each other's
   effects). It auto-detects combat triggers (an attack landing on a
   hostile) and stages a `CombatStart` + initiative rolls.
5. **DM** narrates the turn's outcomes (one DMNarration per turn).
6. If narration succeeds, the buffer commits atomically. If narration
   fails after retries, the entire intent-derived state rolls back
   (the actor's prose still commits as a PlayerAction).

Replay is exact: given the same event log and the same RNG seed, the
projected world state is identical.

---

## The gate report

The demo's six scenario criteria, in order from most-reliable to
most-content-dependent:

| Criterion | What triggers it |
|---|---|
| Warden engagement | Any `<talk>` / `<attack>` / combat involving `ent_warden` |
| `<use_item/>` | A healing potion drunk OR lockpicks used |
| `<check/>` | At least one skill check (Sylvi's insight on Aldous is the seeded one) |
| `<puzzle_answer/>` | The riddle door's "echo" solved |
| NPC narration | At least one `DMNarration` event caused by an NPC's own turn |
| Heartstone countdown | Heartstone picked up, 5-turn countdown ticked |

Five-of-six is the demo's documented pass threshold. Six-of-six is
achievable when both PCs make goal-directed choices and the party
splits the dungeon between optimal-path (Brakka via flooded passage)
and puzzle-path (Sylvi via riddle door) approaches.
