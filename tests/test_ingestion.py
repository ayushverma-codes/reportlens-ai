import fitz
import pytest
from src.ingestion.validator import validate_pdf, PDFValidationError
from src.ingestion.pdf_loader import load_pdf

def make_pdf(text='Example annual report with a revenue table.'):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72,72), text)
    out = doc.tobytes()
    doc.close()
    return out

def test_valid_pdf_and_page_provenance():
    raw = make_pdf()
    doc = load_pdf(raw,'example.pdf',extract_page_tables=False)
    assert validate_pdf(raw) == 1
    assert doc.pages[0].pdf_page_number == 1
    assert doc.pages[0].filename == 'example.pdf'
    assert 'revenue table' in doc.pages[0].text

def test_invalid_bytes_rejected():
    with pytest.raises(PDFValidationError):
        validate_pdf(b'not a pdf')

def test_password_protected_rejected():
    doc = fitz.open(); doc.new_page()
    data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw='secret', user_pw='password')
    doc.close()
    with pytest.raises(PDFValidationError, match='Password'):
        validate_pdf(data)

def test_empty_page_is_tracked():
    doc = fitz.open(); doc.new_page(); data = doc.tobytes(); doc.close()
    result = load_pdf(data,'blank.pdf',extract_page_tables=False)
    assert result.pages[0].status == 'warning'
    assert result.summary['problematic_pages'] == 1
