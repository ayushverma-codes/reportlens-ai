"""Regression cases for conversational Infosys revenue follow-up on Streamlit Cloud."""

from src.conversation_context import resolve_followup_question
from src.document_routing import AUTO, catalog, select_docs
from src.fast_rag import (connect_database, generate_answer, list_documents,
                          store_document, year_starts)


def context():
    db = connect_database()
    contents = [
        ('infosys-ar-25.pdf', 2025, 2024, '1,62,990', '1,53,670'),
        ('infosys-ar-26.pdf', 2026, 2025, '1,78,650', '1,62,990'),
    ]
    for filename, a, b, amount_a, amount_b in contents:
        text = (f'Infosys Consolidated Statement of Profit and Loss (₹ crore).\n'
                f'Year ended March 31, {a} and March 31, {b}.\n'
                f'Revenue from operations 12 {amount_a} {amount_b}.\n'
                f'Profit for the year 99 12,345 11,111.')
        store_document(db, filename, filename, 'pdf', 400, 300,
                       [('PDF page 287', text)])
    groups = catalog([{'filename': 'TCS_Annual_Report_2025-26.pdf',
                       'doc_id': 'tcs'}], list_documents(db))
    return db, groups


def test_infosys_followup_rewrites_revenue_years_and_company():
    db, groups = context()
    try:
        history = [
            {'role': 'user', 'content': 'Compare TCS and Infosys revenue in FY 2025-26'},
            {'role': 'assistant', 'content': 'Comparison table.'},
            {'role': 'user', 'content': 'What was Infosys revenue in FY 2024–25?'},
            {'role': 'assistant', 'content': '₹1,62,990 crore [S1].'},
        ]
        current = 'How much did it increase in FY 2025–26, both in ₹ crore and percentage?'
        question = resolve_followup_question(current, history, groups)
        assert 'Infosys' in question
        assert 'revenue' in question.lower()
        assert year_starts(question) == {2024, 2025}
        allowed, clarification, company = select_docs(question, groups, AUTO, history)
        assert clarification is None
        assert company == 'Infosys'
        assert allowed == groups['Infosys']
        # The existing deterministic extractor should give both amounts, a
        # cited absolute difference, and the growth percentage without Groq.
        result = generate_answer(question, None, db, history, '', 'unused',
                                 allowed_doc_ids=allowed, company_scope=company)
        assert '15,660' in result['answer']
        assert '9.61%' in result['answer']
        assert '1,62,990' in result['answer']
        assert '1,78,650' in result['answer']
        assert len(result['sources']) >= 2
        assert all(s['filename'].startswith('infosys') for s in result['sources'])
    finally:
        db.close()


def test_different_explicit_company_never_inherits_infosys():
    db, groups = context()
    try:
        h = [{'role':'user','content':'What was Infosys revenue in FY 2024-25?'}]
        q = 'What was TCS revenue in FY 2025-26?'
        assert resolve_followup_question(q, h, groups) == q
        q2 = 'What did it say about TCS revenue in FY 2025-26?'
        assert resolve_followup_question(q2, h, groups) == q2
    finally:
        db.close()


def test_multi_company_comparison_does_not_imply_a_single_company():
    db, groups = context()
    try:
        h = [{'role':'user','content':'Compare TCS and Infosys revenues FY 2025-26'},
             {'role':'assistant','content':'Both companies have revenue.'}]
        q = 'How much did it increase in FY 2025-26?'
        assert resolve_followup_question(q, h, groups) == q
    finally:
        db.close()


def test_standalone_new_question_not_rewritten():
    db, groups = context()
    try:
        h = [{'role':'user','content':'What was Infosys revenue in FY 2024-25?'}]
        q = 'Annual revenues'
        assert resolve_followup_question(q, h, groups) == q
    finally:
        db.close()


def test_simple_pronoun_inherits_single_company_and_year():
    db, groups = context()
    try:
        h = [{'role':'user','content':'What was Infosys revenue in FY 2024-25?'}]
        q = resolve_followup_question('What about its profit?', h, groups)
        assert 'Infosys' in q
        assert 'profit' in q
        assert year_starts(q) == {2024}
    finally:
        db.close()


def test_no_history_leaves_ambiguous_question_unchanged():
    db, groups = context()
    try:
        q = 'How much did it increase in FY 2025-26?'
        assert resolve_followup_question(q, [], groups) == q
    finally:
        db.close()
