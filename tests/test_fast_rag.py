import io
import os
from pathlib import Path

import pytest

from src.fast_rag import (
    DB_PATH, connect_database, list_documents, pdf_chunks, csv_chunks,
    store_document, delete_document, retrieve, year_starts, generate_answer,
)


def test_reference_count_and_revenue_retrieval():
    db = connect_database(DB_PATH, readonly=True)
    docs = list_documents(db)
    assert len(docs) == 4
    assert sum(d['page_count'] for d in docs) == 1382
    hits = retrieve('What was TCS consolidated revenue from operations in FY 2022-23?', db, None)
    assert hits
    assert hits[0]['filename'] == 'annual-report-2022-2023.pdf'
    assert any('225,458' in h['content'] or '2,25,458' in h['content'] for h in hits)
    db.close()


def test_csv_ingestion_search_and_removal():
    data = b'Name,Department,Revenue\nAlice,Sales,100\nBob,Tech,200\nCarol,Sales,300\n'
    row_count, chunks = csv_chunks(data)
    assert row_count == 3
    assert any('total 600' in content for _, content in chunks)
    db = connect_database()
    store_document(db, 'csv1', 'sales.csv', 'csv', row_count, len(data), chunks)
    hits = retrieve('What was Alice revenue?', None, db)
    assert any('Alice' in h['content'] and h['location'] == 'CSV row 2' for h in hits)
    delete_document(db, 'csv1')
    assert not list_documents(db)
    assert retrieve('Alice revenue', None, db) == []
    db.close()


def test_temporary_session_isolation():
    data = b'Patient,Visits\nSomeone,12\n'
    row_count, chunks = csv_chunks(data)
    a, b = connect_database(), connect_database()
    store_document(a, 'first', 'secret.csv', 'csv', row_count, len(data), chunks)
    assert retrieve('Someone Visits', None, a)
    assert not retrieve('Someone Visits', None, b)
    a.close(); b.close()


def test_future_year_abstains_without_groq():
    db = connect_database(DB_PATH, readonly=True)
    result = generate_answer('What was TCS revenue in FY 2030-31?', db, None,
                             [], 'dummy_test_key', 'openai/gpt-oss-20b')
    assert result['sources'] == []
    assert 'couldn\'t find' in result['answer']
    db.close()


def test_pdf_first_pages_extraction():
    # The prebuilt reference index is tested independently; avoid bundling 80MB originals.
    from pymupdf import open as pdf_open
    pdf = pdf_open()
    page = pdf.new_page()
    page.insert_text((50,70), 'Revenue from operations 225458 crore')
    data = pdf.tobytes()
    pdf.close()
    pages, chunks = pdf_chunks(data)
    assert pages == 1
    assert chunks and 'Revenue' in chunks[0][1]


def test_decompression_not_needed_for_reference_reports():
    db = connect_database(DB_PATH,readonly=True)
    assert sum(d['chunk_count'] for d in list_documents(db)) > 3000
    db.close()


def test_two_pdf_uploads_can_be_searched_together():
    import pymupdf
    db = connect_database()
    for i, value in enumerate(('125000', '135000'), start=1):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((50,75), f'ACME yearly revenue from operations: {value} crore')
        data = doc.tobytes(); doc.close()
        n_pages, chunks = pdf_chunks(data)
        store_document(db, f'pdf{i}', f'ACME-202{i}-202{i+1}.pdf', 'pdf', n_pages, len(data), chunks)
    hits = retrieve('ACME revenue from operations', None, db)
    assert {h['filename'] for h in hits} == {'ACME-2021-2022.pdf', 'ACME-2022-2023.pdf'}
    db.close()


def test_short_revenue_question_returns_four_cited_fiscal_years():
    from src.fast_rag import annual_metric_summary
    db = connect_database(DB_PATH, readonly=True)
    try:
        for q in ('revenues', 'annual revenues', 'annual revenue'):
            response = generate_answer(q, db, None, [], '', 'openai/gpt-oss-20b')
            assert len(response['sources']) >= 3
            for amount in ('2,25,458', '2,40,893', '2,55,324', '2,67,021'):
                assert amount in response['answer']
            assert 'PDF page' in response['sources'][0]['location']
    finally:
        db.close()


def test_year_filter_points_to_relevant_financial_statement():
    db = connect_database(DB_PATH, readonly=True)
    try:
        questions = [
            ('FY 2022-23 revenue from operations', 'annual-report-2022-2023.pdf', 'PDF page 191'),
            ('FY 2023-24 revenue from operations', 'annual-report-2023-2024.pdf', 'PDF page 181'),
            ('FY 2025-26 total consolidated expenses', 'TCS_Annual_Report_2025-26.pdf', 'PDF page 167'),
        ]
        for question, filename, location in questions:
            hits = retrieve(question, db, None)
            assert hits[0]['filename'] == filename
            assert hits[0]['location'] == location
    finally:
        db.close()


def test_cross_report_comparison_gets_both_financial_statements():
    db = connect_database(DB_PATH, readonly=True)
    try:
        hits = retrieve('Compare consolidated revenue FY 2022-23 and FY 2023-24', db, None)
        result = {(x['filename'],x['location']) for x in hits}
        assert ('annual-report-2022-2023.pdf', 'PDF page 191') in result
        assert ('annual-report-2023-2024.pdf', 'PDF page 181') in result
    finally:
        db.close()
