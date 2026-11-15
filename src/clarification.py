"""Resolve a user's short reply to a document-choice clarification.

No external request; only company/file names in the current catalog can complete
an outstanding question. A new substantive question cancels the pending intent.
"""
from __future__ import annotations

import re
from pathlib import Path

from src.document_routing import company_mentions


FILLER_WORDS = frozenset({
    'the', 'company', 'file', 'report', 'reports', 'please', 'use', 'choose',
    'select', 'for', 'i', 'want', 'mean', 'one', 'annual', 'pdf', 'only',
})


def complete_company_question(reply: str, pending_question: str | None,
                              groups: dict[str, set[str]]) -> str | None:
    """Turn 'Annual revenues' -> 'Infosys' into 'Annual revenues for Infosys'.

    Returns None when the reply is not *only* a company/file selection.
    This avoids carrying an old topic into a completely new question.
    """
    if not pending_question or not reply.strip():
        return None
    mentioned = company_mentions(reply, groups)
    if len(mentioned) != 1:
        return None
    name = mentioned[0]
    remainder = reply.lower()
    if name.startswith('File: '):
        filename = name[len('File: '):]
        remainder = remainder.replace(filename.lower(), ' ')
        remainder = remainder.replace(Path(filename).stem.lower(), ' ')
    else:
        remainder = re.sub(r'(?<!\w)' + re.escape(name.lower()) + r'(?!\w)', ' ', remainder)
        if name == 'TCS':
            remainder = remainder.replace('tata consultancy services', ' ')
    leftovers = set(re.findall(r'[a-z0-9]+', remainder)) - FILLER_WORDS
    if leftovers:
        return None
    return f'{pending_question.strip().rstrip("?.! ")} for {name}'
