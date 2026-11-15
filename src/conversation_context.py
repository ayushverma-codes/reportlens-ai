"""Conservative, session-only interpretation of short conversational follow-ups.

This rewrites *intent*, never copies financial values from an earlier model answer.
Fresh retrieval and citation verification still happen on every factual turn.
"""
from __future__ import annotations

import re

from src.document_routing import company_mentions
from src.fast_rag import metric_type, year_starts


# These are referential constructions, not broad subject keywords. A standalone
# question about a different named company must never inherit an older scope.
_REFERENCE = re.compile(
    r"\b(?:it|its|they|their|them|that|those|same|earlier|previous|"
    r"former|latter|what about|how much did|how much has|and what|and for)\b",
    re.I,
)
_CHANGE = re.compile(
    r"\b(?:increas\w*|decreas\w*|chang\w*|growth|grew|difference|"
    r"rise|rose|fall|fell)\b",
    re.I,
)


def _fiscal_label(start: int) -> str:
    return f"FY {start}-{(start + 1) % 100:02d}"


def resolve_followup_question(question: str, history: list[dict] | None,
                              groups: dict[str, set[str]]) -> str:
    """Ground an ambiguous follow-up in the most recent unambiguous user turn.

    Example:
      'What was Infosys revenue in FY 2024-25?'
      'How much did it increase in FY 2025-26, in crore and percent?'

    becomes a comparison involving Infosys revenue in both years, which the
    existing deterministic extractor can verify against the selected PDFs.

    Never rely on previous *assistant answers* for figures or company facts.
    Do not inherit from an earlier multi-company comparison, or from history
    after an unrelated new standalone question.
    """
    original = question.strip()
    if not original or not history or not _REFERENCE.search(original):
        return original

    current_mentions = company_mentions(original, groups)
    if len(current_mentions) > 1:
        return original

    # Treat a new, explicitly named company as an intentional scope change.
    # A single named company with no referential signal is left untouched above.
    recent_users = [m.get('content', '').strip() for m in history
                    if m.get('role') == 'user' and m.get('content', '').strip()]
    if not recent_users:
        return original

    # The most recent user turn that explicitly names a company is the boundary
    # of conversational scope. In particular, do not choose one company from a
    # multi-company comparison.
    previous_company = None
    previous_statement = None
    for text in reversed(recent_users):
        names = company_mentions(text, groups)
        if len(names) > 1:
            return original
        if len(names) == 1:
            previous_company = names[0]
            previous_statement = text
            break
        # Do not skip a substantive standalone request and revive an old topic.
        if len(text.split()) >= 4 and not _REFERENCE.search(text):
            return original

    if previous_company is None or previous_statement is None:
        return original
    if current_mentions and current_mentions != [previous_company]:
        return original

    # A precise comparison requires a matching metric and two identifiable
    # fiscal periods. If these cannot be established, keep the original intent
    # and inherit only the company to avoid making up missing years.
    current_metric = metric_type(original)
    earlier_metric = metric_type(previous_statement)
    metric = current_metric or earlier_metric
    current_years = year_starts(original)
    previous_years = year_starts(previous_statement)
    if (_CHANGE.search(original) and metric in ('revenue', 'profit', 'expenses')
            and len(current_years) == 1 and len(previous_years) == 1
            and current_years != previous_years):
        prior = next(iter(previous_years))
        target = next(iter(current_years))
        metric_title = {
            'revenue': 'consolidated revenue from operations',
            'profit': 'consolidated profit for the year',
            'expenses': 'consolidated total expenses',
        }[metric]
        return (f'Compare {previous_company} {metric_title} from '
                f'{_fiscal_label(prior)} to {_fiscal_label(target)}. '
                'Calculate the increase or decrease in ₹ crore and percentage.')

    # For a simple pronoun question, preserve the exact user topic. Add a
    # missing fiscal year only when the previous question had exactly one.
    rewritten = original
    if not current_mentions:
        rewritten = f'{rewritten.rstrip(" ?")}, for {previous_company}?'
    if metric and not current_metric:
        rewritten = f'{rewritten.rstrip(" ?")}, regarding {metric}?'
    if not current_years and len(previous_years) == 1:
        prior = next(iter(previous_years))
        rewritten = f'{rewritten.rstrip(" ?")} in {_fiscal_label(prior)}?'
    return rewritten
