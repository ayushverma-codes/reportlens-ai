"""Conservative source-grounded financial summaries for session PDF uploads.

For short revenue/profit/expense questions, use figures extracted from the
consolidated P&L, never guessed or supplied by a language model. This handles
several annual-report PDFs belonging to the SAME selected company.
"""
from __future__ import annotations

import re
import sqlite3
from collections import defaultdict

from src.fast_rag import doc_year, _format_indian, metric_type, year_starts


_METRICS = {
    'revenue': (r'^\s*revenue\s+from\s+operations\b', 'Consolidated revenue from operations'),
    'expenses': (r'^\s*total\s+expenses\b', 'Consolidated total expenses'),
    'profit': (r'^\s*profit\s+for\s+the\s+year\b', 'Consolidated profit for the year'),
}
_CONSOLIDATED_PL = re.compile(
    r'\bconsolidated\s+(?:statement\s+of\s+)?'
    r'(?:profit\s+and\s+loss|income\s+statement|statement\s+of\s+comprehensive\s+income)\b',
    re.I,
)


def _is_financial_summary_request(question: str) -> bool:
    """Do not replace growth, explanations, or comparisons with a simple table."""
    if metric_type(question) not in _METRICS or len(year_starts(question)) > 1:
        return False
    return not re.search(
        r'\b(why|how|growth|margin|segment|geograph\w*|industry|risk|'
        r'strategy|ratio|percentage|compare|comparison|versus|vs\.?|difference|'
        r'higher|lower|increase|decrease|change)\b', question, re.I
    )


def _clean_amount(value: str) -> int | None:
    if not re.fullmatch(r'\d{1,3}(?:,\d{2,3})*|\d+', value):
        return None
    n = int(value.replace(',', ''))
    return n if 100 <= n <= 1_000_000_000 else None


def _financial_row(page: str, metric: str) -> list[int]:
    """Read the two numeric data cells of a P&L row, even when PDF text is
    extracted into separate lines/columns.

    Avoid following another named row, footnote, or table heading. A decimal
    note identifier (such as 2.18) is NOT a monetary amount.
    """
    pattern, _ = _METRICS[metric]
    lines = page.splitlines()

    def integers(s: str) -> list[int]:
        # Prevent a financial note number like 2.18 from looking like 2 and 18.
        without_notes = re.sub(r'(?<!\d)\d{1,3}(?:\.\d{1,3})+(?!\d)', ' ', s)
        values = []
        for match in re.finditer(r'(?<![\w.])\d[\d,]*(?![\w.%])', without_notes):
            value = _clean_amount(match.group())
            if value is not None:
                values.append(value)
        return values

    for i, line in enumerate(lines):
        match = re.match(pattern, line, re.I)
        if not match:
            continue
        values = integers(line[match.end():])
        if len(values) >= 2:
            return values[-2:]
        # In several annual reports, 'Revenue from operations', note 2.18,
        # 1,78,650 and 1,62,990 occupy four different extracted lines.
        for next_line in lines[i + 1:i + 9]:
            stripped = next_line.strip()
            if not stripped:
                continue
            # Numeric-only lines (including note references) are data cells.
            # Stop before reading another financial statement row.
            if not re.fullmatch(r'[\d,.()₹₹ \t–—-]+', stripped):
                break
            values.extend(integers(stripped))
            if len(values) >= 2:
                return values[-2:]
        return []
    return []


def _year_columns(page: str, filename: str) -> list[int]:
    """Identify the actual two table columns with evidence of year-end dates.

    Handles both 'Year ended March 31, 2026 March 31, 2025' and the
    very common table layout 'Year ended March 31,' followed by a new
    header row '2026 2025'. Never infer the columns from filename alone.
    """
    head = page[:4000]
    lines = head.splitlines()
    expected_start = doc_year(filename)
    expected_end = expected_start + 1 if expected_start is not None else None
    date_header = re.compile(
        r'\byear\s+ended\s+(?:march\s*31|31\s*march)\b', re.I
    )
    for i, line in enumerate(lines):
        m = date_header.search(line)
        if not m:
            continue
        # Limit scan to the table heading, not later narrative disclosures.
        rest = line[m.end():] + '\n' + '\n'.join(lines[i + 1:i + 7])
        rest = rest[:180]
        # Require two *adjacent* year labels in the first few header cells.
        years = [int(x) for x in re.findall(r'(?<!\d)20\d{2}(?!\d)', rest)]
        # Repeated headings may include two copies of the current year.
        years = list(dict.fromkeys(years))
        if len(years) < 2:
            continue
        if years[0] != years[1] + 1:
            continue
        if expected_end is not None and years[0] != expected_end:
            continue
        return years[:2]

    # Some reports place 'Year ended Year ended' above the next header line
    # 'Note  March 31, 2023  March 31, 2022'. These are still explicit dates.
    direct_dates = [int(x) for x in re.findall(
        r'(?:march\s*31|31\s*march)\s*,?\s*(20\d{2})\b',
        head[:1800], re.I
    )]
    direct_dates = list(dict.fromkeys(direct_dates))
    if (len(direct_dates) >= 2 and direct_dates[0] == direct_dates[1] + 1
            and (expected_end is None or direct_dates[0] == expected_end)):
        return direct_dates[:2]
    return []


def _merge_chunks(chunks: list[str]) -> str:
    """Restore page text from overlapping same-page chunks."""
    if not chunks:
        return ''
    merged = chunks[0]
    for chunk in chunks[1:]:
        overlap = 0
        for n in range(min(400, len(merged), len(chunk)), 29, -1):
            if merged.endswith(chunk[:n]):
                overlap = n
                break
        merged += chunk[overlap:] if overlap else '\n' + chunk
    return merged


def _page_groups(conn: sqlite3.Connection, doc_id: str):
    rows = conn.execute(
        'SELECT location, content FROM chunks WHERE doc_id=? ORDER BY id', (doc_id,)
    ).fetchall()
    groups: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if row['location'].startswith('PDF page '):
            groups[row['location']].append(row['content'])
    for location, chunks in groups.items():
        yield location, _merge_chunks(chunks)


def _extract_statement(document: dict, db: sqlite3.Connection, metric: str) -> list[dict]:
    """Return only figures with year, metric, unit and source-page support."""
    results = []
    for location, text in _page_groups(db, document['doc_id']):
        plain = re.sub(r'\s+', ' ', text)
        if not _CONSOLIDATED_PL.search(plain):
            continue
        if not re.search(r'\bcrores?\b', plain, re.I):
            continue
        amounts = _financial_row(text, metric)
        years = _year_columns(text, document['filename'])
        # Financial row and year header must form a complete mapping.
        if not amounts or not years or len(amounts) != len(years):
            continue
        # Reject sources that do not clearly state rupees.
        # Reports may print the ₹ glyph as ` or H; neither proves a currency.
        unit = '₹ crore' if re.search(r'₹|\bINR\b|\bRs\.?\b|\brupees\b', plain[:1500], re.I) else 'crore (currency unverified)'
        for index, (ending, amount) in enumerate(zip(years, amounts)):
            results.append({
                'ending': ending, 'amount': amount,
                'is_current': index == 0,
                'filename': document['filename'],
                'doc_id': document['doc_id'],
                'location': location, 'page': text,
                'unit': unit,
            })
        # A consolidated P&L statement is normally one page. Use only the
        # first verified page to avoid picking contradictory note disclosures.
        break
    return results


def single_upload_financial_summary(
    question: str,
    temporary: sqlite3.Connection | None,
    allowed_doc_ids: set[str] | None,
    company_scope: str = '',
) -> dict | None:
    """Deterministic summary for one OR MANY selected PDF uploads.

    None means this is not a suitable request. For a suitable request, return
    verified table rows or an explicit abstention; never delegate financial
    figures to the LLM if a summary can't be grounded.
    """
    if temporary is None or allowed_doc_ids is None or not _is_financial_summary_request(question):
        return None
    selected = [dict(r) for r in temporary.execute('SELECT * FROM documents ORDER BY filename')
                if r['doc_id'] in allowed_doc_ids]
    if not selected:
        return None   # e.g. permanent TCS reports only
    # A mix of PDFs and CSVs cannot be summarized with the P&L-specific parser.
    if any(d['kind'] != 'pdf' for d in selected):
        return None
    # Only process one company at a time. For cross-company comparison normal
    # retrieval should gather evidence from both; never blend annual rows.
    if not company_scope or ',' in company_scope:
        return None

    metric = metric_type(question)
    display_metric = _METRICS[metric][1]
    figures = []
    for doc in selected:
        figures.extend(_extract_statement(doc, temporary, metric))
    if not figures:
        files = ', '.join(d['filename'] for d in selected)
        return {
            'answer': (f'I found {files}, but could not reliably extract '
                       f'{display_metric.lower()} from a consolidated financial statement. '
                       'I will not guess a value or use a subsidiary or standalone table.'),
            'sources': [],
        }

    by_year: dict[int, list[dict]] = defaultdict(list)
    for fig in figures:
        by_year[fig['ending']].append(fig)
    requested = year_starts(question)
    eligible_years = sorted(y for y in by_year if not requested or y - 1 in requested)
    if not eligible_years:
        return {
            'answer': ('That financial year is not verifiable from the selected '
                       'uploaded reports; no figure has been inferred.'),
            'sources': [],
        }

    lines = [f'**{company_scope} — {display_metric}**', '',
             '| Financial year (ends 31 March) | Reported amount | Source |',
             '|---|---:|---|']
    source_ids = {}
    sources = []
    ambiguities = []
    added_rows = 0
    for year in eligible_years:
        records = by_year[year]
        unique_amounts = {r['amount'] for r in records}
        if len(unique_amounts) > 1:
            ambiguities.append(f'FY {year-1}–{str(year)[-2:]} (conflicting figures across reports)')
            continue
        # Choose the reporting year's OWN statement if available; fall back
        # to a later report's comparative column only if values agree.
        chosen = sorted(records, key=lambda x: (not x['is_current'], x['filename']))[0]
        identity = (chosen['doc_id'], chosen['location'])
        if identity not in source_ids:
            label = f'S{len(sources) + 1}'
            source_ids[identity] = label
            sources.append({'id': label, 'filename': chosen['filename'],
                            'location': chosen['location'],
                            'excerpt': chosen['page'][:650]})
        label = source_ids[identity]
        unit = chosen['unit']
        displayed_amount = (f'₹{_format_indian(chosen["amount"])} crore'
                            if unit == '₹ crore'
                            else f'{_format_indian(chosen["amount"])} {unit}')
        lines.append(f'| FY {year-1}–{str(year)[-2:]} | '
                     f'{displayed_amount} | [{label}] |')
        added_rows += 1
    if not added_rows:
        return {
            'answer': ('The selected reports contain conflicting or incomplete '
                       'financial-year figures. I cannot verify a reliable answer.'),
            'sources': [],
        }
    if ambiguities:
        lines += ['', '**Not shown:** ' + '; '.join(ambiguities) + '.']
    lines += ['', '*Only values extracted from the uploaded consolidated '
              'financial statements are included. Missing years are not estimated.*']
    return {'answer': '\n'.join(lines), 'sources': sources}


def reject_inconsistent_fiscal_year_labels(question: str, generated: str) -> str | None:
    """Block contradictions such as '2025-26 (FY2025)' in LLM tables."""
    if metric_type(question) is None:
        return None
    for line in generated.splitlines():
        matches = re.findall(
            r'\b(20\d{2})\s*[-–—/]\s*(20\d{2}|\d{2})\s*\(\s*FY\s*(20\d{2})\s*\)',
            line, re.I
        )
        for start_s, end_s, fy_s in matches:
            start = int(start_s)
            ending = int(end_s) if len(end_s) == 4 else (start // 100 * 100 + int(end_s))
            if ending < start:
                ending += 100
            if int(fy_s) != ending or ending != start + 1:
                return (
                    'The generated financial table used contradictory fiscal-year '
                    'labels, so I withheld it rather than display potentially '
                    'misassigned amounts. Please request a specific year or consult '
                    'the cited consolidated statement.'
                )
    return None


def reject_unsupported_future_years(question: str, generated: str,
                                    documents: list[dict]) -> str | None:
    """Withhold an LLM financial table that reports future-year actuals."""
    if metric_type(question) is None:
        return None
    if re.search(r'\b(forecast|projection|projected|estimate|guidance|expected)\b',
                 question, re.I):
        return None
    report_ends = [year + 1 for d in documents if d.get('kind') == 'pdf'
                   for year in [doc_year(d.get('filename', ''))]
                   if year is not None]
    if not report_ends or len(report_ends) != len(documents):
        return None
    last_year = max(report_ends)
    answer_years = set()
    for match in re.finditer(
        r'\b(?:FY\s*)?(20\d{2})\s*[-–—/]\s*(20\d{2}|\d{2})\b', generated, re.I
    ):
        suffix = match.group(2)
        ending = int(suffix) if len(suffix) == 4 else int(match.group(1)[:2] + suffix)
        if ending >= int(match.group(1)):
            answer_years.add(ending)
    for match in re.finditer(r'\bFY\s*(20\d{2})\b', generated, re.I):
        answer_years.add(int(match.group(1)))
    for match in re.finditer(r'\b(?:year\s+ended|as\s+at)\s+(?:31\s+march|march\s+31)[, ]+\s*(20\d{2})\b', generated, re.I):
        answer_years.add(int(match.group(1)))
    unsupported = sorted(y for y in answer_years if y > last_year)
    if not unsupported:
        return None
    label = ', '.join('FY ' + str(y) for y in unsupported)
    return (f'I cannot verify annual financial figures for {label} from the '
            f'selected reports. Their latest identifiable reporting year ends '
            f'in {last_year}. The generated response included an unsupported '
            'period, so I have withheld its entire table rather than display '
            'potentially misleading figures. Ask for a specific year covered '
            'by the reports.')
