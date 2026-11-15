"""Reproduces the reported 'Annual revenues' -> 'Infosys' -> subsidiaries bug."""

import pymupdf

from src.clarification import complete_company_question
from src.document_routing import AUTO, catalog, select_docs
from src.fast_rag import (
    DB_PATH, connect_database, list_documents, pdf_chunks,
    store_document, generate_answer,
)


def _make_upload():
    # Mock a multi-page PDF in which a subsidiaries page is full of Infosys terms
    # but a separate, grounded financial statement contains the revenue amounts.
    pdf = pymupdf.open()
    subsidiaries = pdf.new_page()
    subsidiaries.insert_text((40, 55), 'Infosys Subsidiaries and Holding Percentages', fontsize=12)
    subsidiaries.insert_text((40, 85), 'Infosys China 100% Infosys Mexico 100%', fontsize=10)
    subsidiaries.insert_text((40, 105), 'Infosys Technologies subsidiaries holding 2025 and 2024', fontsize=10)
    statement = pdf.new_page()
    statement.insert_text((40, 60), 'Infosys Consolidated Statement of Profit and Loss', fontsize=12)
    statement.insert_text((40, 85), '(INR crore)', fontsize=10)
    statement.insert_text((40, 105), 'Year ended March 31, 2026 March 31, 2025', fontsize=10)
    statement.insert_text((40, 125), 'Revenue from operations 12 1,78,650 1,62,990', fontsize=10)
    statement.insert_text((40, 145), 'Total expenses 1,00,000 95,000', fontsize=10)
    data = pdf.tobytes()
    pdf.close()
    count, chunks = pdf_chunks(data)
    ref = connect_database(DB_PATH, readonly=True)
    temp = connect_database()
    store_document(temp, 'synthetic_infosys', 'infosys-ar-26.pdf', 'pdf', count, len(data), chunks)
    return ref, temp


def test_clarification_keeps_revenue_intent():
    ref, temp = _make_upload()
    try:
        groups = catalog(list_documents(ref), list_documents(temp))
        ids, question, _ = select_docs('Annual revenues', groups, AUTO)
        assert not ids and question and 'Which company' in question
        resolved = complete_company_question('Infosys', 'Annual revenues', groups)
        assert resolved == 'Annual revenues for Infosys'
        ids, clarification, company = select_docs(resolved, groups, AUTO)
        assert not clarification and company == 'Infosys'
        answer = generate_answer(resolved, ref, temp, [], '', 'openai/gpt-oss-20b',
                                 allowed_doc_ids=ids, company_scope=company)
        assert '1,78,650' in answer['answer']
        assert '1,62,990' in answer['answer']
        assert 'FY 2025–26' in answer['answer']
        assert 'Subsidiaries' not in answer['answer']
        assert len(answer['sources']) == 1
        assert answer['sources'][0]['location'] == 'PDF page 2'
        assert answer['sources'][0]['filename'] == 'infosys-ar-26.pdf'
    finally:
        ref.close()
        temp.close()


def test_new_question_does_not_inherit_annual_revenue():
    groups = {'TCS': {'one'}, 'Infosys': {'two'}}
    assert complete_company_question('What subsidiaries does Infosys own?',
                                     'annual revenues', groups) is None
    assert complete_company_question('TCS report please',
                                     'annual revenues', groups) == 'annual revenues for TCS'


def test_no_verified_financial_page_does_not_guess():
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((40, 80), 'Infosys subsidiaries and holding percentages are 100%', fontsize=11)
    data = pdf.tobytes()
    pdf.close()
    count, chunks = pdf_chunks(data)
    conn = connect_database()
    store_document(conn, 'bad', 'infosys-ar-26.pdf', 'pdf', count, len(data), chunks)
    try:
        answer = generate_answer('Infosys annual revenues', None, conn, [], '', 'openai/gpt-oss-20b',
                                 allowed_doc_ids={'bad'}, company_scope='Infosys')
        assert not answer['sources']
        assert 'could not reliably extract' in answer['answer']
        assert 'Subsidiaries and Holding Percentages' not in answer['answer']
    finally:
        conn.close()


def test_explicit_infosys_fiscal_year_revenue_is_company_scoped():
    ref, temp = _make_upload()
    try:
        groups = catalog(list_documents(ref), list_documents(temp))
        ids, err, company = select_docs('What was Infosys revenue in FY 2025-26?', groups)
        assert not err
        result = generate_answer('What was Infosys revenue in FY 2025-26?', ref, temp,
                                 [], '', 'openai/gpt-oss-20b',
                                 allowed_doc_ids=ids, company_scope=company)
        assert '1,78,650' in result['answer']
        assert '1,62,990' not in result['answer']
        assert result['sources'][0]['filename'] == 'infosys-ar-26.pdf'
    finally:
        ref.close()
        temp.close()


def test_future_year_guard_rejects_repeated_previous_year_amount():
    from src.financial_summary import reject_unsupported_future_years
    docs = [{'kind': 'pdf', 'filename': 'infosys-ar-26.pdf'}]
    answer = (
        '| FY2025 | 162990 [S1] |\n'
        '| FY2026 | 178650 [S2] |\n'
        '| FY2026-27 (FY2027) | 178650 [S2] |'
    )
    refusal = reject_unsupported_future_years('Infosys annual revenues', answer, docs)
    assert refusal and 'FY 2027' in refusal
    assert 'withheld' in refusal
    assert reject_unsupported_future_years('Infosys annual revenues',
                                           '| FY2025 | 162990 |\n| FY2026 | 178650 |', docs) is None


def test_future_year_guard_does_not_guess_unknown_document_period():
    from src.financial_summary import reject_unsupported_future_years
    answer = '| FY2027 | 12345 [S1] |'
    assert reject_unsupported_future_years('revenue', answer,
                                           [{'kind': 'pdf', 'filename': 'annual.pdf'}]) is None


def test_future_year_guard_no_false_positive_for_nonnumeric_question():
    from src.financial_summary import reject_unsupported_future_years
    assert reject_unsupported_future_years('Explain FY2027 strategic risks',
                                           'Management discussed FY2027.',
                                           [{'kind': 'pdf', 'filename': 'infosys-ar-26.pdf'}]) is None
