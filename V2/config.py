"""
M3 configuration — the single tuning point for retry + fallback behavior.

The brief's "one place in config" rule (m3_build_brief.md) exists so that
retry behavior cannot silently drift across modules. If you change a
value here, the next test run reflects it; if a caller wants per-run
overrides (tests, `m3_demo --stress`, etc.) they pass an explicit value
to `DMAgent(retry_cap=...)` or `run_turn(..., retry_cap=...)`.

These constants are intentionally module-level (not a class) so they
can be read with `import config; config.RETRY_CAP` without instantiation
overhead and so that monkey-patching in tests is trivial.
"""
from __future__ import annotations


# Maximum number of RETRIES per beat (initial attempt is in addition to
# this). RETRY_CAP=3 means up to 4 LLM calls per beat: 1 initial + 3
# retries. Set to 0 to revert to M2 behavior (single shot, fallback on
# first failure). Higher values trade latency for recovery odds — at
# ~5s/call on qwen3:14b, RETRY_CAP=3 caps a fallback path at ~20s.
RETRY_CAP = 3


# Fallback `DMNarration.text` written to the log when retries are
# exhausted. These exist so the player always gets a visible beat
# (otherwise the turn produces only a player_action in the log, with
# no DM response). Wording is deliberately meta — italic-style
# parenthesized text — so it cannot be mistaken for in-fiction prose.
FALLBACK_INTENT_TEXT = (
    "(The moment hangs in the air; nothing decisive happens this turn.)"
)
FALLBACK_NARRATION_TEXT = (
    "(The action resolves, but the moment passes without clear narration.)"
)


# Debug log file name. Written into the same directory as `events.jsonl`
# and `measurements.json` for the run; one JSONL record per exhausted
# retry (see debug_log.py).
DEBUG_LOG_FILENAME = "debug.jsonl"


# ---------------------------------------------------------------------------
# M4: player agent
# ---------------------------------------------------------------------------


# Cap on the player's freeform text per turn. Longer outputs are truncated
# with an ellipsis. Players don't need to write essays; the DM has to parse
# what they said, and very long actions tend to be a model hallucinating
# scenes rather than declaring an action.
MAX_PLAYER_OUTPUT_CHARS = 500


# Substituted when the player LLM returns empty (after stripping). The DM
# will see this as a no-action turn; mechanically equivalent to passing.
# Meta-styled like the M3 fallback texts so it cannot be confused with
# in-fiction prose.
PLAYER_FALLBACK_TEXT = "(I take no action.)"


# ---------------------------------------------------------------------------
# M6: summarizer
# ---------------------------------------------------------------------------


# Per-prompt character budget for the player's view-rendered prompt. When
# `_estimate_player_prompt_chars` exceeds this, the summarizer fires before
# the next PC turn. char_count / 4 ≈ tokens; 8000 chars ≈ 2000 tokens —
# generous headroom under qwen3:14b's 32k context, leaving room for the
# DM's own prompts and completion budget elsewhere.
PROMPT_CHAR_BUDGET = 8000


# Hard cap on a single summary's text length. The provider's LLM is asked
# for concision; if it overshoots, the wrapper truncates with an ellipsis
# before appending. Keeps any one summary from itself bloating the prompt.
MAX_SUMMARY_CHARS = 1500


# ---------------------------------------------------------------------------
# M8: turn protocol
# ---------------------------------------------------------------------------


# Safety cap on the number of intents the player agent can plan per
# turn. Not a TTRPG rule — a sanity check that prevents a runaway LLM
# from declaring 50 looks. dnd5e_lite's action-economy rules separately
# cap the action/bonus/move counts; this is the catch-all upper bound.
MAX_INTENTS_PER_TURN = 6


# ---------------------------------------------------------------------------
# M9: combat-end + status taxonomy
# ---------------------------------------------------------------------------


# Statuses that count as "neutralized" for combat-end purposes and for
# the scheduler's dead-PC skip. M5 used "dead" only; M9 extends to the
# full set, matching real TTRPG fleeing/surrender semantics.
NEUTRALIZED_STATUSES = frozenset({"dead", "fled", "knocked_out", "surrender"})


# How many consecutive turns must pass with no two combat participants
# in the same location before combat auto-ends via disengage. Per the
# M9 design discussion: "two or so turns... unless they don't see each
# other." Tunable here.
DISENGAGE_TURN_WINDOW = 2


# Attribute name used to mark an NPC as having a pending response turn
# in exploration mode. Set by the runner via AttributeSet when (a) a PC
# directs a <talk target=npc> at them, or (b) a PC moves into their
# location and the NPC is hostile. Read by the scheduler to interleave
# NPC turns in front of the usual PC rotation. Leading underscore is a
# convention marking it as a system attribute, not a fictional one
# (compare to seed-authored `persona`, `hp`, etc.).
PENDING_NPC_RESPONSE_ATTR = "_pending_response_seq"


# Number of consecutive empty-intent turns from a single PlayerAgent
# before the next prompt gets a forward-progress override clause. The
# escalation tells the player they MUST emit an <intent> tag this turn.
# Threshold 2 gives one "free pass" turn of pure narration before the
# system intervenes — the floor at which we treat the LLM as stuck,
# not deliberately RP-pausing. Observed in M9 runs: a curious-to-a-
# fault persona can spend 12+ consecutive turns examining the same
# object without ever emitting a structured intent. The escalation
# breaks that loop.
EMPTY_INTENT_ESCALATION_THRESHOLD = 2


# Number of consecutive turns a player has taken in their CURRENT
# location (with no intervening move) before the next prompt gets a
# room-stickiness pressure clause referencing the party's goals.
# Threshold 3 fires on the 4th turn in the same room: enough budget to
# arrive, establish, take an action, and follow up before the system
# nudges the PC to move on. Observed M9 failure mode: a PC anchored to
# an NPC (negotiator persona + scene mystery) emits valid <talk>
# intents indefinitely. <talk> defeats the empty-intent escalation
# because it IS an intent; this counter catches the looser "no spatial
# progress" pattern those repeated talks produce.
ROOM_STICKINESS_ESCALATION_THRESHOLD = 3
