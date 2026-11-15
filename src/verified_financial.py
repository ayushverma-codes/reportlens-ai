"""Small, generic deterministic extractors for explicitly dated financial facts.

Source documents, not benchmark answers, supply all values. If a statement or
financial-year mapping is ambiguous, return None and let normal RAG handle it.
"""
from __future__ import annotations

import re
from typing import Any


def _source(hit: dict, identifier: str = 'S1') -> dict:
    return {
        'id': identifier,
        'filename': hit['filename'],
        'location': hit['location'],
        'excerpt': hit['content'][:550],
    }


def _clean_number(value: str) -> int:
    return int(value.replace(',', ''))


def _comparison(question: str, permanent: Any, temporary: Any,
                allowed_doc_ids: set[str] | None) -> dict | None:
    from src.fast_rag import (_statement_hits, _metric_row, metric_type,
                              year_starts, doc_year, _format_indian)
    starts = sorted(year_starts(question))
    metric = metric_type(question)
    if len(starts) != 2 or metric not in ('revenue', 'profit', 'expenses'):
        return None
    if not re.search(r'\b(compare|comparison|change|changed|difference|increase|increased|decrease|decreased)\b', question, re.I):
        return None
    if re.search(r'\b(margin|growth rate|why|risk|segment|industry|vertical|client)\b', question, re.I):
        return None
    hits = _statement_hits(permanent, temporary, question, allowed_doc_ids)
    candidates: dict[int, tuple[int, int, dict]] = {}
    for hit in hits:
        y = doc_year(hit['filename'])
        figures = _metric_row(hit, metric)
        if y is None or figures is None:
            continue
        for end_year, value, current in ((y + 1, figures[0], True),
                                         (y, figures[1], False)):
            trust = (2 if current else 1) + (0 if 'ϰ' in hit['content'] else 2)
            if end_year not in candidates or candidates[end_year][0] < trust:
                candidates[end_year] = (trust, value, hit)
    ends = [start + 1 for start in starts]
    if not all(end in candidates for end in ends):
        return None
    (a, b) = [candidates[end][1] for end in ends]
    if a <= 0:
        return None
    label = {'revenue': 'consolidated revenue from operations',
             'profit': 'consolidated profit for the year',
             'expenses': 'consolidated total expenses'}[metric]
    sources, ids = [], {}
    lines = [f'**Comparison of {label}** (₹ crore):', '',
             '| Financial year | Amount |', '|---|---:|']
    for end in ends:
        _, amount, hit = candidates[end]
        identity = (hit['filename'], hit['location'])
        if identity not in ids:
            sid = 'S' + str(len(sources) + 1)
            ids[identity] = sid
            sources.append(_source(hit, sid))
        lines.append(f'| FY {end-1}–{str(end)[-2:]} | ₹{_format_indian(amount)} crore [{ids[identity]}] |')
    change = b - a
    direction = 'increased' if change > 0 else 'decreased' if change < 0 else 'remained unchanged'
    pct = abs(change) / a * 100
    lines.extend(['', f'The amount **{direction}** by **₹{_format_indian(abs(change))} crore** '
                  f'(**{pct:.2f}%**) from FY {starts[0]}–{str(ends[0])[-2:]} '
                  f'to FY {starts[1]}–{str(ends[1])[-2:]}.',
                  '', '*Calculated from the cited financial-statement figures.*'])
    return {'answer': '\n'.join(lines), 'sources': sources}


def _constant_currency(question: str, permanent: Any, temporary: Any,
                       allowed_doc_ids: set[str] | None) -> dict | None:
    from src.fast_rag import doc_year, year_starts
    if not re.search(r'\bconstant[- ]currency\b', question, re.I):
        return None
    if not re.search(r'\b(revenue|growth|change)\b', question, re.I):
        return None
    starts = year_starts(question)
    if len(starts) != 1:
        return None
    for db in (permanent, temporary):
        if db is None:
            continue
        sql = ("SELECT doc_id,filename,location,content FROM chunks "
               "WHERE lower(content) LIKE '%constant currency%' "
               "AND lower(content) LIKE '%revenue%' ORDER BY id")
        for row in db.execute(sql):
            hit = dict(row)
            if allowed_doc_ids is not None and hit['doc_id'] not in allowed_doc_ids:
                continue
            if doc_year(hit['filename']) not in starts:
                continue
            content = hit['content']
            match = re.search(
                r'constant\s+currency\s+revenue.{0,160}?\bgrowth\b.{0,370}?'
                r'(?:decline|decrease|fall)\s+of\s+(\d+(?:\.\d+)?)\s*%',
                content, flags=re.I | re.S,
            )
            if match:
                start = next(iter(starts))
                return {
                    'answer': (f'Constant-currency revenue growth in FY {start}–{str(start+1)[-2:]} '
                               f'was a **decline of {match.group(1)}%** [S1].'),
                    'sources': [_source(hit)],
                }
    return None


def _segment_ranking(question: str, permanent: Any, temporary: Any,
                     allowed_doc_ids: set[str] | None) -> dict | None:
    from src.fast_rag import doc_year, year_starts, _format_indian
    q = question.casefold()
    if 'industry vertical' not in q or 'highest' not in q:
        return None
    by_growth = bool(re.search(r'(?:year.on.year|yoy|growth)', q))
    if not by_growth and not re.search(r'\brevenue\b', q):
        return None
    starts = year_starts(question)
    if len(starts) != 1:
        return None
    line_re = re.compile(
        r'^\s*(?P<name>[A-Za-z][A-Za-z ,&/()\-]+?)\s+'
        r'(?P<current>\d{1,3}(?:,\d{2,3})+)\s+'
        r'(?P<previous>\d{1,3}(?:,\d{2,3})+)\s+'
        r'(?P<growth>\(?-?\d+(?:\.\d+)?\)?)\s+'
        r'(?P<margin>\d+(?:\.\d+)?)\s+'
        r'(?P<prior_margin>\d+(?:\.\d+)?)\s*$', re.M
    )
    for db in (permanent, temporary):
        if db is None:
            continue
        rows = db.execute(
            "SELECT doc_id,filename,location,content FROM chunks "
            "WHERE lower(content) LIKE '%segment revenue%' "
            "AND lower(content) LIKE '%industry vertical%' ORDER BY id"
        )
        for row in rows:
            hit = dict(row)
            if allowed_doc_ids is not None and hit['doc_id'] not in allowed_doc_ids:
                continue
            if doc_year(hit['filename']) not in starts:
                continue
            if not re.search(r'\bFY\s*' + str(next(iter(starts)) + 1) + r'\b', hit['content']):
                continue
            matches = []
            for m in line_re.finditer(hit['content']):
                name = ' '.join(m.group('name').split())
                if name.casefold() in ('total', 'segment revenue'):
                    continue
                value = _clean_number(m.group('current'))
                growth = float(m.group('growth').strip('()'))
                if m.group('growth').startswith('('):
                    growth = -growth
                matches.append((name, value, growth))
            if len(matches) < 4:
                continue
            name, value, growth = max(matches, key=lambda r: r[2] if by_growth else r[1])
            start = next(iter(starts))
            if by_growth:
                answer = (f'The highest year-on-year revenue growth among the industry verticals '
                          f'in FY {start}–{str(start+1)[-2:]} was **{name}**, '
                          f'at **{growth:g}%** [S1].')
            else:
                answer = (f'The industry vertical with the highest revenue '
                          f'in FY {start}–{str(start+1)[-2:]} was **{name}**, '
                          f'with **₹{_format_indian(value)} crore** [S1].')
            return {'answer': answer, 'sources': [_source(hit)]}
    return None


def verified_financial_answer(question: str, permanent: Any, temporary: Any,
                              allowed_doc_ids: set[str] | None) -> dict | None:
    """Return a source-based answer only when the relevant data is unambiguous."""
    from src.document_routing import company_for_doc
    from src.fast_rag import list_documents
    # These parsers compare financial years WITHIN a single organization.
    # A comparison across different companies must keep company identity
    # attached to every financial figure; defer those questions to normal RAG.
    companies = set()
    for db, permanent_flag in ((permanent, True), (temporary, False)):
        if db is None:
            continue
        for doc in list_documents(db):
            if allowed_doc_ids is not None and doc['doc_id'] not in allowed_doc_ids:
                continue
            if doc['kind'] == 'pdf':
                companies.add(company_for_doc(doc, permanent=permanent_flag))
    if len(companies) != 1:
        return None
    for function in (_comparison, _constant_currency, _segment_ranking):
        result = function(question, permanent, temporary, allowed_doc_ids)
        if result is not None:
            return result
    return None
