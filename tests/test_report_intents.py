"""Regression tests for vague report discovery prompts."""
from src.document_routing import AUTO, catalog, select_docs
from src.fast_rag import DB_PATH, connect_database, list_documents, store_document, generate_answer
from src.report_intents import is_document_listing_request


def test_vague_report_queries_are_inventory_requests():
    for question in ('annual reports', 'annual; reports', 'reports',
                     'list annual reports', 'which reports are available?',
                     'show available PDFs', 'what documents do you have?'):
        assert is_document_listing_request(question), question


def test_substantive_questions_not_intercepted():
    for question in ('summarize the annual reports', 'revenue in annual reports',
                     'compare annual reports for risk factors',
                     'What was TCS revenue in FY 2025-26?'):
        assert not is_document_listing_request(question), question


def test_permanent_inventory_without_groq():
    with connect_database(DB_PATH, readonly=True) as permanent:
        result = generate_answer('annual; reports', permanent, None, [], '', 'unused')
    assert len([line for line in result['answer'].splitlines() if line.startswith('- `')]) == 4
    assert '346 pages' in result['answer']
    assert '360 pages' in result['answer']
    assert result['sources'] == []


def test_inventory_respects_csv_and_temporary_scope():
    temporary = connect_database()
    try:
        store_document(temporary,'pdf1','acme-report.pdf','pdf',12,120,[('PDF page 1','Some text')])
        store_document(temporary,'csv1','observations.csv','csv',20,200,[('CSV row 2','some row')])
        with connect_database(DB_PATH, readonly=True) as permanent:
            all_reports = generate_answer('annual reports', permanent, temporary, [], '', 'unused')
            assert 'acme-report.pdf' in all_reports['answer']
            assert 'observations.csv' not in all_reports['answer']
            uploads = generate_answer('list documents', permanent, temporary, [], '', 'unused',
                                      allowed_doc_ids={'pdf1', 'csv1'})
            assert 'acme-report.pdf' in uploads['answer']
            assert 'observations.csv' in uploads['answer']
            assert 'annual-report-2022-2023.pdf' not in uploads['answer']
    finally:
        temporary.close()


def test_inventory_skips_ambiguous_company_clarification():
    with connect_database(DB_PATH, readonly=True) as permanent:
        docs = list_documents(permanent)
    others = [dict(doc_id='acme1', filename='infosys-ar-26.pdf')]
    groups = catalog(docs, others)
    ids, clarification, company = select_docs('annual reports', groups, AUTO, [])
    assert clarification is None
    assert len(ids) == 5
    assert company == 'available documents'
