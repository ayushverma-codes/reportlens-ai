"""Regression cases for the reported TCS+Infosys blended-revenue incident."""
import pymupdf

from src.document_routing import AUTO, COMPARE, catalog, select_docs
from src.fast_rag import (DB_PATH, connect_database, csv_chunks, store_document,
                          list_documents, pdf_chunks, retrieve, generate_answer)


def make_mixed_sources():
    ref = connect_database(DB_PATH, readonly=True)
    temp = connect_database()
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((50, 70), 'Infosys Annual Report 2025-26; Consolidated Statement of Profit and Loss')
    page.insert_text((50, 100), 'Revenue from operations 178650 162990 crore')
    data = pdf.tobytes()
    pdf.close()
    count, chunks = pdf_chunks(data)
    store_document(temp, 'infosys_fixture', 'infosys-ar-26.pdf', 'pdf', count, len(data), chunks)
    groups = catalog(list_documents(ref), list_documents(temp))
    return ref, temp, groups


def test_auto_short_annual_revenue_requests_company_no_model_call():
    ref, temp, groups = make_mixed_sources()
    try:
        for q in ('annual revenues', 'anuual revenue', 'revenues'):
            ids, clarification, company = select_docs(q, groups, AUTO)
            assert ids == set()
            assert clarification and 'TCS' in clarification and 'Infosys' in clarification
    finally:
        ref.close(); temp.close()


def test_explicit_company_limits_retrieval_and_tcs_summary():
    ref, temp, groups = make_mixed_sources()
    try:
        ids, clarification, company = select_docs('TCS annual revenue', groups, AUTO)
        assert not clarification and company == 'TCS'
        summary = generate_answer('TCS annual revenues', ref, temp, [], '',
                                  'openai/gpt-oss-20b', allowed_doc_ids=ids,
                                  company_scope=company)
        assert '2,67,021' in summary['answer']
        assert not any('infosys' in s['filename'].lower() for s in summary['sources'])
        hits = retrieve('TCS revenue FY 2025-26', ref, temp, allowed_doc_ids=ids)
        assert hits and all('infosys' not in h['filename'].lower() for h in hits)

        ids, clarification, company = select_docs('Infosys annual revenue FY 2025-26', groups, AUTO)
        assert not clarification and company == 'Infosys'
        hits = retrieve('Infosys annual revenue FY 2025-26', ref, temp, allowed_doc_ids=ids)
        assert hits and all(h['filename'] == 'infosys-ar-26.pdf' for h in hits)
    finally:
        ref.close(); temp.close()


def test_manual_company_selection_and_comparison():
    ref, temp, groups = make_mixed_sources()
    try:
        ids, error, company = select_docs('annual revenues', groups, 'Infosys')
        assert not error and company == 'Infosys' and ids == groups['Infosys']
        ids, error, company = select_docs('annual revenues', groups, 'TCS')
        assert not error and ids == groups['TCS']
        ids, error, company = select_docs('Compare TCS and Infosys revenue FY 2025-26', groups, AUTO)
        assert not error and ids == groups['TCS'] | groups['Infosys']
        ids, error, company = select_docs('Infosys revenue', groups, 'TCS')
        assert not ids and 'sidebar' in error
    finally:
        ref.close(); temp.close()


def test_no_accidental_topic_linking():
    ref, temp, groups = make_mixed_sources()
    try:
        history = [dict(role='user', content='Who is the chairman of TCS?'),
                   dict(role='assistant', content='N Chandrasekaran')]
        ids, error, company = select_docs('annual revenue', groups, AUTO, history)
        assert ids == set() and error  # New question, not referential.
        ids, error, company = select_docs('name of above person', groups, AUTO, history)
        assert not error and company == 'TCS'
    finally:
        ref.close(); temp.close()


def test_cross_company_retrieval_includes_both_company_files():
    ref, temp, groups = make_mixed_sources()
    try:
        ids, error, _ = select_docs('Compare TCS and Infosys annual revenue FY 2025-26', groups, AUTO)
        assert not error
        hits = retrieve('Compare TCS and Infosys annual revenue FY 2025-26', ref, temp, allowed_doc_ids=ids)
        names = {hit['filename'] for hit in hits}
        assert 'infosys-ar-26.pdf' in names
        assert 'TCS_Annual_Report_2025-26.pdf' in names
    finally:
        ref.close(); temp.close()
