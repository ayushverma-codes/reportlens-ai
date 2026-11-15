"""Regression for two Infosys annual reports and the inconsistent FY table."""
import pymupdf

from src.fast_rag import (
    DB_PATH, connect_database, list_documents, pdf_chunks,
    store_document, generate_answer,
)
from src.document_routing import AUTO, catalog, select_docs
from src.financial_summary import reject_inconsistent_fiscal_year_labels


def _report(filename, ending_year, current, previous):
    pdf = pymupdf.open()
    junk = pdf.new_page()
    junk.insert_text((35, 60), 'List of subsidiary companies and holding percentages', fontsize=11)
    junk.insert_text((35, 82), 'Infosys China 100 percent and Infosys Mexico 100 percent')
    page = pdf.new_page()
    page.insert_text((35, 55), 'Infosys Consolidated Statement of Profit and Loss', fontsize=11)
    page.insert_text((35, 80), '(INR crore)', fontsize=10)
    page.insert_text((35, 100), f'Year ended March 31, {ending_year} March 31, {ending_year - 1}', fontsize=10)
    page.insert_text((35, 125), f'Revenue from operations 12 {current:,} {previous:,}', fontsize=10)
    page.insert_text((35, 145), f'Total expenses {current-40000:,} {previous-40000:,}', fontsize=10)
    data = pdf.tobytes()
    pdf.close()
    return filename, data


def _two_infosys_docs():
    db = connect_database()
    for filename, data in (
        _report('infosys-ar-25.pdf', 2025, 162990, 153670),
        _report('infosys-ar-26.pdf', 2026, 178650, 162990),
    ):
        n, chunks = pdf_chunks(data)
        store_document(db, filename, filename, 'pdf', n, len(data), chunks)
    return db


def test_two_uploaded_reports_annual_revenue_never_calls_llm():
    ref = connect_database(DB_PATH, readonly=True)
    uploads = _two_infosys_docs()
    try:
        groups = catalog(list_documents(ref), list_documents(uploads))
        ids, err, name = select_docs('Infosys annual revenues', groups, AUTO)
        assert not err and name == 'Infosys' and len(ids) == 2
        result = generate_answer('Infosys annual revenues', ref, uploads, [], '',
                                 'model_that_does_not_exist', allowed_doc_ids=ids,
                                 company_scope=name)
        answer = result['answer']
        assert 'FY 2023–24' in answer and '1,53,670' in answer
        assert 'FY 2024–25' in answer and '1,62,990' in answer
        assert 'FY 2025–26' in answer and '1,78,650' in answer
        assert 'FY2025)' not in answer and 'FY 2026–27' not in answer
        assert len(result['sources']) == 2
        assert {s['filename'] for s in result['sources']} == {
            'infosys-ar-25.pdf', 'infosys-ar-26.pdf'
        }
        assert all(s['location'] == 'PDF page 2' for s in result['sources'])
        # FY 2024-25 must point to the financial statement in that year's report,
        # rather than confusing it with the FY 2025-26 comparison column.
        assert '| FY 2024–25 | ₹1,62,990 crore | [S1] |' in answer
        assert '| FY 2025–26 | ₹1,78,650 crore | [S2] |' in answer
    finally:
        uploads.close()
        ref.close()


def test_two_uploaded_reports_explicit_year_is_scoped():
    uploads = _two_infosys_docs()
    try:
        ids = {d['doc_id'] for d in list_documents(uploads)}
        result = generate_answer('Infosys revenue FY2026', None, uploads, [], '',
                                 'fake_model', allowed_doc_ids=ids,
                                 company_scope='Infosys')
        assert 'FY 2025–26' in result['answer'] and '1,78,650' in result['answer']
        assert '1,62,990' not in result['answer']
        no_future = generate_answer('Infosys revenue FY2027', None, uploads, [], '',
                                    'fake_model', allowed_doc_ids=ids,
                                    company_scope='Infosys')
        assert no_future['sources'] == []
        assert 'not verifiable' in no_future['answer']
    finally:
        uploads.close()


def test_ambiguous_conflicting_comparatives_are_omitted():
    uploads = connect_database()
    for filename, data in (
        _report('infosys-ar-25.pdf', 2025, 162990, 153670),
        _report('infosys-ar-26.pdf', 2026, 178650, 162900),
    ):
        n, chunks = pdf_chunks(data)
        store_document(uploads, filename, filename, 'pdf', n, len(data), chunks)
    try:
        ids = {d['doc_id'] for d in list_documents(uploads)}
        result = generate_answer('Infosys annual revenues', None, uploads, [], '',
                                 'fake_model', allowed_doc_ids=ids,
                                 company_scope='Infosys')
        assert 'FY 2024–25 (conflicting' in result['answer']
        assert '| FY 2024–25 |' not in result['answer']
        assert '| FY 2025–26 |' in result['answer']
    finally:
        uploads.close()


def test_inconsistent_fiscal_label_fails_closed():
    bad = '| 2025-26 (FY2025) | 1,62,990 crore | [S4] |'
    assert reject_inconsistent_fiscal_year_labels('Infosys annual revenue', bad)
    good = '| 2025-26 (FY2026) | 1,78,650 crore | [S4] |'
    assert reject_inconsistent_fiscal_year_labels('Infosys annual revenue', good) is None
