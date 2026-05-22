from __future__ import annotations

from backend.app.agents.context_builder import _DM_SYSTEM_PROMPT
from backend.app.services.ollama_client import generate


def build_narration_prompt(
    messages: list[dict[str, str]],
) -> tuple[str, str, str]:
    """Build (prompt, system_prompt, action_text) for Ollama from context message list.

    The first system message becomes the Ollama system prompt (DM rules).
    All remaining system messages (campaign, character, memory, enemies, dice) are
    injected into the prompt body as structured context so the model sees them.
    User/assistant pairs form the conversation history.
    """
    first_system: str = _DM_SYSTEM_PROMPT
    context_parts: list[str] = []
    history_parts: list[str] = []
    action_text = "the action"
    seen_first = False

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "").strip()
        if not content:
            continue
        if role == "system":
            if not seen_first:
                first_system = content
                seen_first = True
            else:
                context_parts.append(content)
        elif role == "user":
            history_parts.append(f"[Player]: {content}")
            action_text = content
        elif role == "assistant":
            history_parts.append(f"[DM]: {content}")

    sections: list[str] = []
    if context_parts:
        sections.append("=== WORLD & CHARACTER STATE ===")
        sections.extend(context_parts)

    if history_parts:
        sections.append("")
        sections.append("=== RECENT HISTORY ===")
        sections.extend(history_parts[:-1])

    sections.append("")
    sections.append("=== CURRENT ACTION ===")
    sections.append(f"Player: {action_text}")
    sections.append("")
    sections.append("Narrate the outcome in 2-3 cinematic sentences.")

    prompt = "\n".join(sections)
    return prompt, first_system, action_text


_MIN_NARRATION_LEN = 30


def narrate(messages: list[dict[str, str]]) -> str:
    """Generate DM narration; retries once if the response is implausibly short."""
    prompt, system_content, action_text = build_narration_prompt(messages)
    result = generate(prompt=prompt, system_prompt=system_content, action_text=action_text)
    if len(result) < _MIN_NARRATION_LEN:
        retry_prompt = (
            prompt
            + "\n\n[The previous response was too brief. "
            "Narrate the outcome in 2-3 full cinematic sentences.]"
        )
        retry = generate(prompt=retry_prompt, system_prompt=system_content, action_text=action_text)
        if len(retry) >= len(result):
            return retry
    return result
