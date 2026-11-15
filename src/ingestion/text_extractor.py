"""Text extraction, retaining individual page provenance and quality warnings."""
import re

def get_page_text(page) -> str:
    return page.get_text('text', sort=True).strip()

def page_warnings(text: str, page_no: int) -> list[str]:
    warnings = []
    if not text:
        warnings.append(f'PDF page {page_no}: no extractable text (possibly scanned)')
    elif len(text) < 80:
        warnings.append(f'PDF page {page_no}: unusually little extractable text')
    if text and (text.count('\ufffd') > 3 or len(re.findall(r'[\x00-\x08]', text)) > 3):
        warnings.append(f'PDF page {page_no}: possible encoding corruption')
    return warnings

def printed_page_number(text: str) -> str | None:
    """Only accept unambiguous isolated numeric page labels; otherwise use PDF page number."""
    lines = [s.strip() for s in text.splitlines() if s.strip()]
    for line in (lines[:2] + lines[-3:]):
        if re.fullmatch(r'\d{1,4}', line):
            return line
    return None
