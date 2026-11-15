"""Transparent deterministic evaluation checks (NOT RAGAS judge scores).

These heuristics deliberately produce *diagnostic* flags only: a number appearing
in the answer or in evidence does NOT establish that a financial statement supports
its association with the requested year/company/currency.
"""
from __future__ import annotations

import re
from statistics import mean

ABSTAIN_RE = re.compile(
    r"(?:could(?:n't| not) find|not (?:available|present|provided|reported)|"
    r"(?:cannot|can't|couldn't|could not) (?:determine|answer|verify|find|establish|confirm)|"
    r"(?:insufficient|lack of|no) (?:information|evidence|data|figure)|"
    r"(?:do(?:es)? not|don't) contain|not in (?:the |these |available )?(?:reports|documents)|"
    r"doesn't (?:contain|provide)|not enough information|unavailable)", re.I)

# Read explicitly declared financial amounts / percentages, not calendar years.
VALUES_RE = re.compile(
    r'(?:₹|Rs\.?\s*|INR\s*|US\$|\$)\s*([\d,]+(?:\.\d+)?)'
    r'|(?<![\w.])([\d,]+(?:\.\d+)?)\s*%'
    r'|(?<!\d)([\d,]+(?:\.\d+)?)\s*(?:crore|billion)\b', re.I)
CITATION_RE = re.compile(r'(?:\[|【)\s*(S\d+)\s*(?:\]|】)')


def money_values(text: str) -> set[str]:
    values = set()
    for match in VALUES_RE.finditer(text or ''):
        raw = next((x for x in match.groups() if x is not None), None)
        if raw:
            try:
                values.add(str(float(raw.replace(',', ''))))
            except ValueError:
                pass
    return values


def value_coverage(reference: str, candidate: str) -> float | None:
    expected = money_values(reference)
    if not expected:
        return None
    # Candidate is a raw PDF excerpt or model output. The financial row may
    # contain a bare number (with a currency/unit only in the table heading).
    # Check number *presence* without interpreting its meaning.
    candidates = re.findall(r'(?<![\d,])(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?(?![\d,])', candidate or '')
    seen = set()
    for raw in candidates:
        try:
            seen.add(str(float(raw.replace(',', ''))))
        except ValueError:
            pass
    return sum(x in seen for x in expected) / len(expected)


def is_abstention(answer: str) -> bool:
    return bool(ABSTAIN_RE.search(answer or ''))


def cited_source_flags(answer: str, sources: list[dict]) -> tuple[bool | None, int]:
    """Citation IDs exist in actual returned sources; does NOT verify claim support."""
    mentions = CITATION_RE.findall(answer or '')
    if not answer:
        return None, 0
    declared = {s['id'] for s in sources}
    return bool(mentions) and all(m in declared for m in mentions), len(mentions)


def doc_coverage(expected_source: str, hits: list[dict]) -> float | None:
    """Fraction of expected source FILES present in top-k evidence, not page recall."""
    if not expected_source or expected_source.casefold().startswith('all four'):
        return None
    required = {v.strip().lower() for v in expected_source.split(';') if v.strip().lower().endswith('.pdf')}
    if not required:
        return None
    returned = {h['filename'].casefold() for h in hits}
    return sum(v in returned for v in required) / len(required)


def aggregate(rows: list[dict]) -> dict:
    """Compute summaries only from completed rows; never convert missing to zero."""
    by_category = {}
    for category in sorted({r['category'] for r in rows}):
        items = [r for r in rows if r['category'] == category]
        completed = [r for r in items if r['status'] in ('answered', 'retrieval_only')]
        scores = {}
        for field in ('retrieval_doc_coverage', 'answer_number_coverage',
                      'evidence_number_coverage', 'abstention_correct', 'citation_ids_valid'):
            values = [r[field] for r in completed if isinstance(r.get(field), (int, float, bool))]
            scores[field] = round(mean(values), 4) if values else None
        by_category[category] = {'questions': len(items), 'completed': len(completed), **scores}
    return {'total_questions': len(rows),
            'answered': sum(r['status'] == 'answered' for r in rows),
            'retrieval_only': sum(r['status'] == 'retrieval_only' for r in rows),
            'error': sum(r['status'] == 'error' for r in rows),
            'by_category': by_category}
