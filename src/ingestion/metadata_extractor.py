"""Best-effort metadata; unknown fields remain null rather than being invented."""
import re

def extract_metadata(pdf_metadata: dict, first_pages: str) -> dict:
    title = (pdf_metadata.get('title') or '').strip() or None
    year = re.search(r'\b(?:20\d{2})\s*[-–/]\s*(?:20)?\d{2}\b', first_pages)
    period = year.group(0) if year else None
    likely_title = next((line.strip() for line in first_pages.splitlines() if re.search(r'annual report|financial report|sustainability report', line, re.I)), None)
    doc_type = ('annual report' if re.search(r'annual report', first_pages[:2500], re.I) else None)
    return {'company': None, 'title': title or likely_title, 'financial_year': period,
            'document_type': doc_type, 'reporting_period': period,
            'pdf_author': pdf_metadata.get('author') or None}
