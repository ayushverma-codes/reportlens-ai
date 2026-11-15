"""Best-effort pdfplumber table extraction with error reporting."""
import io
import pdfplumber

def extract_tables(data: bytes, *, max_pages: int | None = None) -> tuple[dict[int, list[list[list[str]]]], list[str]]:
    tables: dict[int, list[list[list[str]]]] = {}
    warnings: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for i, page in enumerate(pdf.pages):
            if max_pages is not None and i >= max_pages:
                break
            try:
                found = page.extract_tables(table_settings={'vertical_strategy': 'lines', 'horizontal_strategy': 'lines'})
                tables[i] = [
                    [[str(cell).strip() if cell is not None else '' for cell in row] for row in table if row]
                    for table in found if table
                ]
            except Exception as exc:
                warnings.append(f'PDF page {i+1}: table extraction failed ({type(exc).__name__})')
                tables[i] = []
    return tables, warnings
