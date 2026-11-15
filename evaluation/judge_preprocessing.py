"""Transparent RAGAS input preparation; original ground truth is never modified.

For the optional `contextualized` judge mode, numeric-only references to simple
'What was/were ...?' questions are phrased as complete factual sentences.
Presentation-only citation tags are removed from the judge response; the
application's citation evaluation is handled separately.
"""
from __future__ import annotations

import re

_CITATION = re.compile(r"(?:【\s*S\s*\d+\s*】|\[\s*S\s*\d+\s*\])", re.IGNORECASE)
_WHAT_WAS = re.compile(r"^\s*what\s+(was|were)\s+(.+?)\?\s*$", re.IGNORECASE)
_NUMERIC_ANSWER = re.compile(
    r"(?:[₹$]|US\$)?\s*[\d,.]+\s*(?:crore|billion|million|%|percent)?\.?",
    re.IGNORECASE,
)


def clean_for_judge(text: str) -> str:
    text = _CITATION.sub("", text or "")
    text = re.sub(r"\*{1,2}", "", text)
    text = re.sub(r"[\u00a0\u202f\u2009\u2007]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def contextual_reference(question: str, reference: str) -> str:
    """Preserve original values while adding their question-derived subject.

    Deliberately leave more complicated answers unchanged; we must not invent
    a decomposition or silently change the label of an evaluation metric.
    """
    reference = clean_for_judge(reference)
    match = _WHAT_WAS.fullmatch((question or "").strip())
    if match and _NUMERIC_ANSWER.fullmatch(reference):
        auxiliary, subject = match.groups()
        return f"{subject.strip()} {auxiliary.lower()} {reference.rstrip('.')}."
    return reference


def limited_contexts(contexts: list[str], max_contexts: int = 0,
                     max_context_chars: int = 0) -> list[str]:
    """Limit *judge input only*, retaining the original retrieval ordering.

    No relevance re-ranking is performed, and original saved contexts remain
    unchanged. This can change faithfulness scores, so limits are reported.
    """
    if max_contexts < 0 or max_context_chars < 0:
        raise ValueError('Context limits must be >= 0 (0 means unlimited)')
    chosen = list(contexts or [])
    if max_contexts:
        chosen = chosen[:max_contexts]
    if max_context_chars:
        chosen = [context[:max_context_chars] for context in chosen]
    return chosen
