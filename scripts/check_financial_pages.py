"""Diagnose annual revenue extraction directly from locally available PDF files.

Run from project root:
  python -m scripts.check_financial_pages "C:\\path\\infosys-ar-25.pdf" "C:\\path\\infosys-ar-26.pdf"

No Groq API required. Does not store any uploaded report permanently.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from src.financial_summary import _CONSOLIDATED_PL, _financial_row, _year_columns


def inspect(filename: str) -> bool:
    import pymupdf

    path = Path(filename)
    if not path.is_file():
        print(f"NOT FOUND: {path}")
        return False
    print(f"\n{path.name}")
    try:
        with pymupdf.open(path) as doc:
            candidates = []
            for page_index, page in enumerate(doc, start=1):
                text = page.get_text('text', sort=True)
                plain = re.sub(r'\s+', ' ', text)
                if not _CONSOLIDATED_PL.search(plain):
                    continue
                if not re.search(r'\brevenue\s+from\s+operations\b', plain, re.I):
                    continue
                years = _year_columns(text, path.name)
                amounts = _financial_row(text, 'revenue')
                has_crore = bool(re.search(r'\bcrores?\b', plain, re.I))
                candidates.append((page_index, years, amounts, has_crore))
                print(f'  PDF page {page_index}: years={years}, revenue_cells={amounts}, crore_unit={has_crore}')
                if years and amounts and len(years) == len(amounts) and has_crore:
                    print('  VERIFIED ROW: ' + ', '.join(f'FY {end-1}-{end%100:02}: {value:,} crore'
                                                        for end, value in zip(years, amounts)))
                    return True
            if not candidates:
                print('  No consolidated P&L page with revenue row was detected.')
            else:
                print('  Candidate page found, but the financial row could not be safely mapped to years.')
    except Exception as exc:
        print(f'  ERROR: {type(exc).__name__}: {exc}')
    return False


def main(argv: list[str]) -> int:
    if not argv:
        print('Usage: python -m scripts.check_financial_pages "path-to-annual-report.pdf" [...]')
        return 2
    results = [inspect(p) for p in argv]
    return 0 if all(results) else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
