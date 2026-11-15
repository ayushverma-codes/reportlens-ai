"""Ingest pages and tables from PDFs without modifying the original bytes."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
import hashlib
import fitz
from .validator import validate_pdf
from .text_extractor import get_page_text, page_warnings, printed_page_number
from .metadata_extractor import extract_metadata
from .table_extractor import extract_tables

@dataclass
class PageRecord:
    document_id: str
    filename: str
    pdf_page_index: int
    pdf_page_number: int
    printed_page_number: str | None
    text: str
    tables: list = field(default_factory=list)
    status: str = 'ok'
    warnings: list[str] = field(default_factory=list)

@dataclass
class IngestedDocument:
    document_id: str
    filename: str
    metadata: dict
    pages: list[PageRecord]
    warnings: list[str]
    @property
    def summary(self) -> dict:
        return {'filename': self.filename, 'document_id': self.document_id,
                'pages': len(self.pages), 'pages_with_text': sum(bool(p.text) for p in self.pages),
                'tables': sum(len(p.tables) for p in self.pages),
                'problematic_pages': sum(bool(p.warnings) for p in self.pages),
                'warnings': len(self.warnings)}

def load_pdf(data: bytes, filename: str, *, enforce_upload_limit: bool = True,
             extract_page_tables: bool = True) -> IngestedDocument:
    validate_pdf(data, enforce_upload_limit=enforce_upload_limit)
    doc_id = hashlib.sha256(data).hexdigest()
    pages: list[PageRecord] = []
    with fitz.open(stream=data, filetype='pdf') as pdf:
        metadata_raw = dict(pdf.metadata or {})
        for idx, page in enumerate(pdf):
            try:
                text = get_page_text(page)
                warnings = page_warnings(text, idx+1)
                status = 'warning' if warnings else 'ok'
            except Exception as exc:
                text = ''
                warnings = [f'PDF page {idx+1}: text extraction failed ({type(exc).__name__})']
                status = 'error'
            pages.append(PageRecord(doc_id, filename, idx, idx+1,
                printed_page_number(text), text, status=status, warnings=warnings))
    all_warnings = [w for page in pages for w in page.warnings]
    if extract_page_tables:
        try:
            table_map, table_warnings = extract_tables(data)
            all_warnings.extend(table_warnings)
            for idx, tables in table_map.items():
                pages[idx].tables = tables
        except Exception as exc:
            all_warnings.append(f'Table extraction unavailable ({type(exc).__name__}): {exc}')
    metadata = extract_metadata(metadata_raw, '\n'.join(p.text for p in pages[:5]))
    return IngestedDocument(doc_id, filename, metadata, pages, all_warnings)
