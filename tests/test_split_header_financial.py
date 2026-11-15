"""Realistic regression for split financial statement table headers."""
import pymupdf

from src.fast_rag import connect_database, pdf_chunks, store_document, generate_answer
from src.financial_summary import _financial_row, _year_columns


def test_split_header_and_split_revenue_cells():
    text = '''Consolidated Statement of Profit and Loss
(In ₹ crore, except per equity share data)
Particulars
Note
Year ended March 31,
2026
2025
Revenue from operations
2.18
1,78,650
1,62,990
Other income, net
2.19
4,322
3,600'''
    assert _year_columns(text, 'infosys-ar-26.pdf') == [2026, 2025]
    assert _financial_row(text, 'revenue') == [178650, 162990]
    assert _year_columns(text, 'infosys-ar-25.pdf') == []


def test_header_and_cells_same_line():
    text = '''Consolidated Statement of Profit and Loss
(INR crore)
Year ended March 31, 2025 March 31, 2024
Revenue from operations 2.18 162,990 153,670
Other income 3,600 4,711'''
    assert _year_columns(text, 'infosys-ar-25.pdf') == [2025, 2024]
    assert _financial_row(text, 'revenue') == [162990, 153670]


def test_does_not_read_next_row_instead_of_revenue():
    text = '''Consolidated Statement of Profit and Loss
(INR crore)
Year ended March 31,
2026 2025
Revenue from operations
2.18
Other income, net 4,322 3,600'''
    assert _financial_row(text, 'revenue') == []


def test_end_to_end_split_financial_statement_without_groq():
    doc = pymupdf.open()
    page = doc.new_page()
    lines = [
        'Infosys Consolidated Statement of Profit and Loss',
        '(In INR crore)',
        'Particulars',
        'Note',
        'Year ended March 31,',
        '2026 2025',
        'Revenue from operations',
        '2.18',
        '1,78,650',
        '1,62,990',
        'Other income, net',
        '2.19',
        '4,322',
        '3,600',
    ]
    for i, line in enumerate(lines):
        page.insert_text((36, 55 + i * 19), line, fontsize=10)
    data = doc.tobytes()
    doc.close()
    temporary = connect_database()
    pages, chunks = pdf_chunks(data)
    store_document(temporary, 'infosys_sample', 'infosys-ar-26.pdf',
                   'pdf', pages, len(data), chunks)
    try:
        result = generate_answer('Infosys annual revenues', None, temporary,
                                 [], '', 'unused-model',
                                 allowed_doc_ids={'infosys_sample'},
                                 company_scope='Infosys')
        assert '| FY 2025–26 | ₹1,78,650 crore | [S1] |' in result['answer']
        assert '| FY 2024–25 | ₹1,62,990 crore | [S1] |' in result['answer']
        assert result['sources'][0]['location'] == 'PDF page 1'
    finally:
        temporary.close()


def test_two_year_ended_headers_with_note_between_dates():
    text = ("Consolidated Statement of Profit and Loss\n(` crore)\n"
            "Year ended       Year ended\n"
            "Note     March 31, 2023    March 31, 2022\n"
            "Revenue from operations         12   2,25,458   1,91,754")
    assert _year_columns(text, 'annual-report-2022-2023.pdf') == [2023, 2022]
    assert _financial_row(text, 'revenue') == [225458, 191754]
