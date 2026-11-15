"""Choose document/company scope before retrieval, preventing financial data mixing."""
from __future__ import annotations

import re
from pathlib import Path

AUTO = 'Auto — identify company from the question'
COMPARE = 'Compare companies (explicit multi-company questions)'


def company_for_doc(doc: dict, permanent: bool = False) -> str:
    """Label documents conservatively; unknown uploads get their own scope."""
    filename = doc['filename'].lower()
    if permanent or filename.startswith('tcs_') or 'tata_consultancy' in filename:
        return 'TCS'
    if 'infosys' in filename:
        return 'Infosys'
    if 'wipro' in filename:
        return 'Wipro'
    if 'hcltech' in filename or 'hcl_tech' in filename:
        return 'HCLTech'
    if 'reliance' in filename:
        return 'Reliance'
    # Unknown report/dataset: do not guess its company from the filename.
    return 'File: ' + Path(doc['filename']).name


def catalog(permanent_docs: list[dict], upload_docs: list[dict],
            include_permanent: bool = True, include_uploads: bool = True) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {}
    if include_permanent:
        for d in permanent_docs:
            groups.setdefault(company_for_doc(d, permanent=True), set()).add(d['doc_id'])
    if include_uploads:
        for d in upload_docs:
            groups.setdefault(company_for_doc(d), set()).add(d['doc_id'])
    return groups


def company_mentions(question: str, groups: dict[str, set[str]]) -> list[str]:
    q = question.casefold()
    mentioned = []
    for name in groups:
        if name.startswith('File: '):
            stem = Path(name[6:]).stem.casefold()
            if stem and stem in q:
                mentioned.append(name)
            continue
        synonyms = {'TCS': ['tcs', 'tata consultancy services'],
                    'Infosys': ['infosys'], 'Wipro': ['wipro'],
                    'HCLTech': ['hcltech', 'hcl tech'],
                    'Reliance': ['reliance']} .get(name, [name.casefold()])
        if any(re.search(r'(?<!\w)' + re.escape(token) + r'(?!\w)', q) for token in synonyms):
            mentioned.append(name)
    return mentioned


def is_reference_followup(question: str) -> bool:
    q = question.casefold().strip()
    return bool(re.search(
        r'\b(above|previous|earlier|that person|this person|same company|that company|its |their |his |her |him |them |what about|and what|and for)\b', q
    ))


def select_docs(question: str, groups: dict[str, set[str]],
                selection: str = AUTO, history: list[dict] | None = None
                ) -> tuple[set[str], str | None, str]:
    """Return allowed IDs, clarification (if ambiguous), and selected company names."""
    if not groups:
        return set(), 'There are no indexed documents in this search scope.', ''
    mentions = company_mentions(question, groups)
    names = list(groups)
    if selection == COMPARE and len(groups) > 1 and re.search(
            r'\b(compare|comparison|across companies|all companies|versus|vs\.?|differences?)\b',
            question, re.I):
        selected = mentions if len(mentions) > 1 else names
        ids = set().union(*(groups[name] for name in selected))
        return ids, None, ', '.join(selected)

    if selection not in (AUTO, COMPARE):
        if selection not in groups:
            return set(), 'The selected company or file is no longer available.', ''
        if mentions and any(n != selection for n in mentions):
            return set(), (f'Your question mentions {", ".join(mentions)}, but the selected source is '
                           f'{selection}. Choose the matching source in the sidebar.'), ''
        return set(groups[selection]), None, selection

    # Generic file-catalog requests do not need company clarification.
    # Route them across the available scope; the answer uses metadata only.
    from src.report_intents import is_document_listing_request
    if is_document_listing_request(question):
        selected_ids = set().union(*groups.values())
        return selected_ids, None, 'available documents'

    if len(mentions) == 1:
        chosen = mentions[0]
        return set(groups[chosen]), None, chosen
    if len(mentions) > 1:
        if re.search(r'\b(compare|comparisons?|versus|vs\.?|difference|different|higher|lower|both)\b', question, re.I):
            ids = set().union(*(groups[n] for n in mentions))
            return ids, None, ', '.join(mentions)
        return set(), ('Your question mentions several companies. Please ask a comparison question '
                       'or choose one company in the sidebar.'), ''
    if len(groups) == 1:
        name = names[0]
        return set(groups[name]), None, name

    # Resolve genuine reference follow-ups, not a new short topic like "annual revenue".
    if history and is_reference_followup(question):
        for msg in reversed(history):
            if msg.get('role') == 'user':
                previous = company_mentions(msg.get('content', ''), groups)
                if len(previous) == 1:
                    return set(groups[previous[0]]), None, previous[0]

    choices = ', '.join(names)
    return set(), (f'Which company or file do you want to analyze? Available: {choices}. '
                   'Mention its name in the question or choose it in the sidebar. '
                   'I will not mix financial figures from different companies.'), ''
