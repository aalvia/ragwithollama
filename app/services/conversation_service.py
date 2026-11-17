"""Memoria de sesión. Solo opera cuando CONVERSATION_CONTEXT=true."""

from __future__ import annotations


class ConversationMemory:
    """Guarda en memoria los últimos turnos de cada sesión del navegador."""

    def __init__(self, enabled: bool, max_turns: int) -> None:
        if max_turns < 1:
            raise ValueError("CONVERSATION_MAX_TURNS debe ser al menos 1")
        self.enabled = enabled
        self.max_turns = max_turns
        self._sessions: dict[str, list[dict[str, str]]] = {}

    def history(self, session_id: str | None) -> list[dict[str, str]]:
        if not self.enabled or not session_id:
            return []
        return [dict(item) for item in self._sessions.get(session_id, [])]

    def remember(self, session_id: str | None, question: str, answer: str) -> None:
        if not self.enabled or not session_id:
            return
        turns = self._sessions.setdefault(session_id, [])
        turns.append({"role": "user", "content": question})
        turns.append({"role": "assistant", "content": answer})
        limit = self.max_turns * 2
        if len(turns) > limit:
            del turns[:-limit]

    def clear(self) -> None:
        self._sessions.clear()
