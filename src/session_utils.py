"""Explicit session cleanup operations, shared by UI and regression tests."""
from __future__ import annotations

from src.fast_rag import connect_database


def clear_conversation(state) -> None:
    """New chat resets history/clarification but keeps indexed uploads."""
    state['messages'] = []
    state['pending_question'] = None
    state['awaiting_company_question'] = None


def clear_private_uploads(state) -> None:
    """Discard the session-only SQLite database and current chat."""
    old = state['private_index']
    old.close()
    state['private_index'] = connect_database()
    clear_conversation(state)
