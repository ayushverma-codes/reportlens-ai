"""Validate actual PDF bytes; limits are for public uploads, not development fixtures."""
import fitz
from config.settings import settings

class PDFValidationError(ValueError):
    pass

def validate_pdf(data: bytes, *, enforce_upload_limit: bool = True) -> int:
    if not data or not data.startswith(b'%PDF-'):
        raise PDFValidationError('Not a valid PDF header')
    if enforce_upload_limit and len(data) > settings.max_file_bytes:
        raise PDFValidationError('PDF exceeds 20 MiB per-file upload limit')
    try:
        doc = fitz.open(stream=data, filetype='pdf')
        try:
            if doc.needs_pass:
                raise PDFValidationError('Password-protected PDF is unsupported')
            if not doc.page_count:
                raise PDFValidationError('PDF contains no pages')
            if doc.page_count > settings.max_pages:
                raise PDFValidationError('PDF exceeds 500-page limit')
            return doc.page_count
        finally:
            doc.close()
    except PDFValidationError:
        raise
    except Exception as exc:
        raise PDFValidationError(f'Cannot open PDF: {type(exc).__name__}') from exc
