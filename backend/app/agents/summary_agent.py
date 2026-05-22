from __future__ import annotations

import json as _json
import uuid as _uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Summary, Turn
from backend.app.services.ollama_client import generate

_SUMMARY_SYSTEM_PROMPT = (
    "You are the session chronicler for a D&D campaign. "
    "Given a session transcript, write a vivid story-style recap that reads like the closing "
    "page of a chapter in a fantasy novel.\n\n"
    "Structure your summary as:\n"
    "1. One opening sentence setting the scene and tone of the session.\n"
    "2. 5-8 bullet points covering the key events in order:\n"
    "   - Important player decisions and their consequences\n"
    "   - Combat outcomes (who fought, who won, what was lost)\n"
    "   - Meaningful NPC interactions and what was learned\n"
    "   - Discoveries, loot, or secrets uncovered\n"
    "   - Character moments that revealed something about the hero\n"
    "3. One closing sentence hinting at what lies ahead.\n\n"
    "RULES:\n"
    "- Write in past tense, third person: 'The party descended...', 'Aldric struck...'\n"
    "- Use the character's actual name from the transcript — never say 'the player'.\n"
    "- Keep bullet points to one sentence each — vivid but tight.\n"
    "- Never invent events not present in the transcript.\n"
    "- If the session was short, fewer bullets is fine — quality over quantity."
)


async def summarise_session(
    session_id: str,
    db: AsyncSession,
) -> str | None:
    """Generate a bullet-point session summary and persist it to the Summary table."""
    result = await db.execute(
        select(Turn).where(Turn.session_id == session_id).order_by(Turn.created_at.asc()).limit(60)
    )
    turns = result.scalars().all()

    if not turns:
        return None

    transcript_lines: list[str] = []
    for i, turn in enumerate(turns, start=1):
        action_type = f"[{turn.action_type}]" if turn.action_type else ""
        transcript_lines.append(f"Turn {i} {action_type}: {turn.action_text or ''}")
        if turn.attack_result:
            try:
                ar = _json.loads(str(turn.attack_result))
                if ar.get("is_hit"):
                    hit_word = "CRITICAL HIT" if ar.get("is_critical") else "HIT"
                    transcript_lines.append(
                        f"  Combat result: {hit_word} — {ar.get('damage', 0)} damage"
                    )
                else:
                    transcript_lines.append("  Combat result: MISS")
            except (_json.JSONDecodeError, TypeError):
                pass
        if turn.narration:
            transcript_lines.append(f"  DM: {turn.narration}")
        if turn.dice_results and turn.dice_results not in ("{}", "[]"):
            transcript_lines.append(f"  Dice: {turn.dice_results}")

    transcript = "\n".join(transcript_lines)
    if len(transcript) > 8000:
        transcript = transcript[:8000] + "\n... [truncated]"

    prompt = f"Session transcript:\n{transcript}\n\nGenerate a bullet-point summary."

    summary_text = generate(
        prompt=prompt,
        system_prompt=_SUMMARY_SYSTEM_PROMPT,
        action_text="the session",
    )

    if summary_text:
        summary = Summary(
            id=str(_uuid.uuid4()),
            session_id=session_id,
            scene_id=None,
            summary_text=summary_text,
            token_count=len(summary_text.split()),
        )
        db.add(summary)

    return summary_text
