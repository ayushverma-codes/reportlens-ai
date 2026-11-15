from src.ingestion.pdf_loader import load_pdf
from src.processing.chunker import chunk_document
from tests.test_ingestion import make_pdf

def test_chunk_has_source():
    raw = make_pdf()
    doc = load_pdf(raw,'example.pdf',extract_page_tables=False)
    parts = chunk_document(doc)
    assert parts and parts[0].document_id == doc.document_id
    assert parts[0].pdf_page_number == 1

def test_table_retains_headers():
    raw = make_pdf()
    doc = load_pdf(raw,'example.pdf',extract_page_tables=False)
    doc.pages[0].tables = [[['FY','Revenue'],['2023','200'],['2024','250']]]
    tables = [c for c in chunk_document(doc) if c.content_type == 'table']
    assert len(tables) == 1
    assert 'FY | Revenue' in tables[0].text
    assert '2024 | 250' in tables[0].text
