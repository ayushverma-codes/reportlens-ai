"""Regression tests for failures found by auditing results.json."""
import re

from src.fast_rag import DB_PATH, connect_database, generate_answer
from src.report_intents import is_document_listing_request
from evaluation.metrics import cited_source_flags


def test_report_intent_does_not_intercept_financial_controls():
    assert not is_document_listing_request(
        "What controls support TCS's financial reporting according to FY 2025-26 report?"
    )
    assert is_document_listing_request('annual reports')


def test_common_llm_citation_formats_are_counted():
    sources = [{'id': 'S1'}, {'id': 'S2'}]
    assert cited_source_flags('₹42,303 crore【S1】【S2】', sources) == (True, 2)
    assert cited_source_flags('₹42,303 crore [ S1 ]', sources) == (True, 1)
    assert cited_source_flags('₹42,303 crore【S3】', sources) == (False, 1)


def test_calendar_profit_must_not_use_fy_profit_table():
    with connect_database(DB_PATH, readonly=True) as db:
        output = generate_answer(
            "What was TCS's net profit in calendar year 2021?",
            db, None, [], '', 'unused',
        )
    assert 'calendar-year' in output['answer']
    assert '42,303' not in output['answer']
    assert output['sources'] == []


def test_revenue_change_is_grounded_and_calculated_correctly():
    with connect_database(DB_PATH, readonly=True) as db:
        output = generate_answer(
            'How did consolidated revenue change from FY 2023-24 to FY 2024-25?',
            db, None, [], '', 'unused',
        )
    assert '2,40,893' in output['answer']
    assert '2,55,324' in output['answer']
    assert '14,431' in output['answer']
    assert len(output['sources']) >= 1


def test_constant_currency_decline_not_prior_year_growth():
    with connect_database(DB_PATH, readonly=True) as db:
        output = generate_answer(
            'What was TCS constant-currency revenue growth in FY 2025-26?',
            db, None, [], '', 'unused',
        )
    assert 'decline of 2.4%' in output['answer']
    assert 'PDF page 58' in output['sources'][0]['location']


def test_segment_rankings_use_consolidated_fy_table():
    with connect_database(DB_PATH, readonly=True) as db:
        top_revenue = generate_answer(
            'Which industry vertical had the highest revenue in FY 2025-26?',
            db, None, [], '', 'unused',
        )
        top_growth = generate_answer(
            'Which industry vertical had the highest year-on-year revenue growth in FY 2025-26?',
            db, None, [], '', 'unused',
        )
    assert 'Banking, Financial Services and Insurance' in top_revenue['answer']
    assert '1,03,363' in top_revenue['answer']
    assert 'Others' in top_growth['answer']
    assert '19%' in top_growth['answer']
    assert top_growth['sources'][0]['location'] == 'PDF page 59'


def test_client_priority_question_prioritizes_relevant_management_discussion():
    from src.fast_rag import retrieve
    with connect_database(DB_PATH, readonly=True) as db:
        hits = retrieve('What client priorities were highlighted in FY 2025-26?', db, None)
    assert hits[0]['filename'] == 'TCS_Annual_Report_2025-26.pdf'
    assert hits[0]['location'] == 'PDF page 58'
    assert 'vendor consolidation' in hits[0]['content']


def test_cross_company_financial_comparison_does_not_take_single_company_shortcut():
    from src.fast_rag import store_document
    from src.verified_financial import verified_financial_answer
    temporary = connect_database()
    try:
        store_document(temporary, 'infosys-test', 'infosys-ar-26.pdf', 'pdf', 1, 300,
                       [('PDF page 1', 'Consolidated Statement of Profit and Loss. '
                         'March 31, 2026 March 31, 2025. Revenue from operations '
                         '1,78,650 1,62,990. This is a test document.')])
        with connect_database(DB_PATH, readonly=True) as db:
            allowed = {r['doc_id'] for r in db.execute('SELECT doc_id FROM documents')}
            allowed.add('infosys-test')
            result = verified_financial_answer(
                'Compare TCS and Infosys revenue from FY 2023-24 to FY 2024-25',
                db, temporary, allowed)
        assert result is None
    finally:
        temporary.close()


def test_full_generation_normalizes_fullwidth_citation(monkeypatch):
    import sys
    from types import SimpleNamespace
    from src.fast_rag import store_document

    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content='The proof point is stated【S1】.')
            )])

    class FakeGroq:
        def __init__(self, **kwargs):
            pass

        @property
        def chat(self):
            return SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, 'groq', SimpleNamespace(Groq=FakeGroq))
    temporary = connect_database()
    try:
        store_document(temporary, 'proof1', 'sample.pdf', 'pdf', 1, 140,
                       [('PDF page 1', 'The proof point is stated on this page.')])
        output = generate_answer('Explain the proof point', None, temporary,
                                 [], 'fake-test-key', 'fake-test-model')
        assert '[S1]' in output['answer']
        assert output['sources'][0]['location'] == 'PDF page 1'
    finally:
        temporary.close()


def test_targeted_resume_preserves_unselected_benchmark_records(tmp_path):
    from evaluation.evaluate import run
    base = dict(mode='retrieval', directory=tmp_path, top_k=2,
                model='unused', sleep=0, resume=False, limit=2)
    rows = run(**base)
    assert {r['id'] for r in rows} == {'Q01','Q02'}
    baseline_answer = next(r['answer'] for r in rows if r['id'] == 'Q02')
    rows2 = run(**(base | dict(resume=True, rerun_ids={'Q01'})))
    assert {r['id'] for r in rows2} == {'Q01','Q02'}
    assert next(r['answer'] for r in rows2 if r['id']=='Q02') == baseline_answer
