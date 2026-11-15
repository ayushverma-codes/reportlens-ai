"""Phase 8 integration checks. No Groq quota, network, or Streamlit server needed."""
from __future__ import annotations

import io
import sqlite3
import sys
from dataclasses import dataclass
from types import SimpleNamespace

import pymupdf
import pytest

from src.clarification import complete_company_question
from src.document_routing import AUTO, catalog, select_docs
from src.fast_rag import (
    CSV_LIMIT, MAX_PAGES, PDF_LIMIT, TOTAL_UPLOAD_LIMIT, DB_PATH,
    connect_database, content_id, csv_chunks, delete_document, generate_answer,
    list_documents, pdf_chunks, retrieve, store_document,
)
from src.response_safety import (
    INVALID_CITATIONS, safe_answer_error, validate_generated_citations,
)
from src.session_utils import clear_conversation, clear_private_uploads
from src.upload_policy import plan_session_uploads, safe_filename


@dataclass
class FakeUpload:
    name: str
    value: bytes
    size_override: int | None = None

    @property
    def size(self):
        return len(self.value) if self.size_override is None else self.size_override

    def getvalue(self):
        return self.value


def make_pdf(text: str | None = None, pages: int = 1, password: bool = False) -> bytes:
    pdf = pymupdf.open()
    for index in range(pages):
        page = pdf.new_page()
        if text:
            page.insert_text((45, 80), f'{text} Page number {index + 1}.')
    kwargs = ({'encryption': pymupdf.PDF_ENCRYPT_AES_256,
               'owner_pw': 'owner', 'user_pw': 'user'} if password else {})
    result = pdf.tobytes(**kwargs)
    pdf.close()
    return result


def ingest(db, candidate):
    if candidate.kind == 'pdf':
        count, chunks = pdf_chunks(candidate.data)
    else:
        count, chunks = csv_chunks(candidate.data)
    return store_document(db, candidate.doc_id, candidate.filename,
                          candidate.kind, count, len(candidate.data), chunks)


def test_upload_name_sanitization_and_extension_policy():
    assert safe_filename(r'C:\fakepath\annual.pdf') == 'annual.pdf'
    assert safe_filename('../sales.csv') == 'sales.csv'
    assert safe_filename('danger\nously.pdf') == 'dangerously.pdf'
    plan = plan_session_uploads([FakeUpload('malware.exe', b'A')], [])
    assert not plan.candidates and 'PDF or CSV' in plan.errors[0]


def test_upload_preflight_respects_per_file_size_without_reading_large_upload():
    huge_pdf = FakeUpload('huge.pdf', b'%PDF-', size_override=PDF_LIMIT + 1)
    huge_csv = FakeUpload('huge.csv', b'x', size_override=CSV_LIMIT + 1)
    plan = plan_session_uploads([huge_pdf, huge_csv], [])
    assert len(plan.errors) == 2 and not plan.candidates
    assert '20 MiB' in plan.errors[0] and '10 MiB' in plan.errors[1]


def test_upload_preflight_checks_actual_bytes_as_well():
    plan = plan_session_uploads([FakeUpload('file.csv', b'x' * (CSV_LIMIT + 1), 1)], [])
    assert not plan.candidates and plan.errors


def test_upload_batch_caps_file_count_and_combined_bytes_without_mutation():
    candidates = [FakeUpload(f'f{i}.csv', f'X,Y\n{i},1\n'.encode()) for i in range(6)]
    plan = plan_session_uploads(candidates, [])
    assert not plan.candidates and 'maximum of 5' in plan.errors[-1]
    existing = [{'doc_id': 'old', 'byte_count': TOTAL_UPLOAD_LIMIT - 1}]
    plan = plan_session_uploads([FakeUpload('extra.csv', b'X,Y\n1,2\n')], existing)
    assert not plan.candidates and '50 MiB' in plan.errors[-1]


def test_upload_deduplicates_existing_and_same_batch_but_allows_distinct_same_name():
    one, two = b'col\nalpha\n', b'col\nbeta\n'
    plan = plan_session_uploads([FakeUpload('report.csv', one), FakeUpload('report.csv', one),
                                 FakeUpload('report.csv', two)], [])
    assert len(plan.candidates) == 2 and plan.duplicates == 1
    repeat = plan_session_uploads([FakeUpload('another.csv', one)],
                                  [{'doc_id': content_id(one), 'byte_count': len(one)}])
    assert not repeat.candidates and repeat.duplicates == 1


def test_end_to_end_five_pdfs_ingest_retrieve_and_delete():
    uploads = [FakeUpload(f'Acme-{i}.pdf', make_pdf(
        f'Acme reporting year financial operations revenue for project {i}'))
        for i in range(5)]
    plan = plan_session_uploads(uploads, [])
    assert len(plan.candidates) == 5 and not plan.errors
    db = connect_database()
    try:
        for c in plan.candidates:
            assert ingest(db, c) > 0
        assert len(list_documents(db)) == 5
        found = retrieve('Acme financial operations project', None, db)
        assert found
        old_id = plan.candidates[0].doc_id
        delete_document(db, old_id)
        assert len(list_documents(db)) == 4
        assert all(h['doc_id'] != old_id for h in retrieve('Acme financial operations', None, db))
        # Deleted content must be absent from both table and FTS.
        assert db.execute('SELECT COUNT(*) FROM chunks WHERE doc_id=?', (old_id,)).fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?',
                          ('"project"',)).fetchone()[0] > 0
    finally:
        db.close()


def test_pdf_integrity_empty_corrupt_password_and_scanned():
    with pytest.raises(ValueError, match='not a PDF'):
        pdf_chunks(b'wrong bytes')
    with pytest.raises(ValueError, match='corrupted|unsupported'):
        pdf_chunks(b'%PDF-1.7\nnot a valid PDF')
    # PyMuPDF refuses to serialize a zero-page PDF. Simulate that decoded state
    # to exercise our check without depending on an invalid on-disk fixture.
    class EmptyDocument:
        needs_pass = False
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def __len__(self): return 0
    import unittest.mock as mock
    with mock.patch.object(pymupdf, 'open', return_value=EmptyDocument()):
        with pytest.raises(ValueError, match='no pages'):
            pdf_chunks(b'%PDF-1.7 fixture')
    with pytest.raises(ValueError, match='Password-protected'):
        pdf_chunks(make_pdf('A secret report contains details', password=True))
    with pytest.raises(ValueError, match='OCR'):
        pdf_chunks(make_pdf(text=None))


def test_pdf_page_limit_enforced_before_extraction():
    fixture = make_pdf(pages=MAX_PAGES + 1)
    with pytest.raises(ValueError, match='500-page'):
        pdf_chunks(fixture)


def test_pdf_size_limit_enforced_before_parsing():
    with pytest.raises(ValueError, match='20 MiB'):
        pdf_chunks(b'%PDF-' + b'X' * PDF_LIMIT)


def test_csv_bad_content_and_numeric_aggregation():
    for bad in (b'', b'\0\0'):
        with pytest.raises(ValueError):
            csv_chunks(bad)
    with pytest.raises(ValueError, match='no data rows'):
        csv_chunks(b'Name,Revenue\n')
    rows, chunks = csv_chunks(b'SalesPerson,Revenue\nA,100\nB,200\nC,50\n')
    assert rows == 3
    assert any('total 350' in text for _, text in chunks)
    assert any('average 116.667' in text for _, text in chunks)


def test_temporary_data_never_leaks_between_independent_sessions():
    a, b = connect_database(), connect_database()
    try:
        data = b'Customer,SecretProject\nPrivate_Alpha,Quantum_Z\n'
        item = plan_session_uploads([FakeUpload('private.csv', data)], []).candidates[0]
        ingest(a, item)
        assert retrieve('Private_Alpha Quantum_Z', None, a)
        assert not list_documents(b)
        assert retrieve('Private_Alpha Quantum_Z', None, b) == []
    finally:
        a.close(); b.close()


def test_chat_reset_preserves_index_but_clear_uploads_removes_it():
    db = connect_database()
    state = {'private_index': db, 'messages':[{'role':'user','content':'secret'}],
             'pending_question':'old', 'awaiting_company_question':'old'}
    try:
        item = plan_session_uploads([FakeUpload('secret.csv', b'Name,Revenue\nAlice,123\n')], []).candidates[0]
        ingest(db, item)
        clear_conversation(state)
        assert list_documents(db) and not state['messages']
        assert state['pending_question'] is None and state['awaiting_company_question'] is None
        clear_private_uploads(state)
        assert state['private_index'] is not db
        assert not list_documents(state['private_index'])
        with pytest.raises(sqlite3.ProgrammingError):
            db.execute('SELECT 1')
    finally:
        state['private_index'].close()


def test_company_scope_and_clarification_do_not_mix_sources():
    ref = connect_database(DB_PATH, readonly=True)
    private = connect_database()
    try:
        pdf = make_pdf('Infosys consolidated revenue from operations amounted to 178650 crore')
        upload = plan_session_uploads([FakeUpload('infosys-ar-26.pdf', pdf)], []).candidates[0]
        ingest(private, upload)
        groups = catalog(list_documents(ref), list_documents(private))
        ids, message, company = select_docs('Annual revenues', groups, AUTO)
        assert not ids and 'Which company' in message
        resolved = complete_company_question('Infosys', 'Annual revenues', groups)
        assert resolved == 'Annual revenues for Infosys'
        ids, message, company = select_docs(resolved, groups, AUTO)
        assert not message and company == 'Infosys'
        hits = retrieve('Infosys revenue', ref, private, allowed_doc_ids=ids)
        assert hits and {h['filename'] for h in hits} == {'infosys-ar-26.pdf'}
        ids, message, company = select_docs('Compare Infosys and TCS revenue FY 2025-26', groups, AUTO)
        assert not message and ids == groups['TCS'] | groups['Infosys']
        hits = retrieve('Compare Infosys and TCS revenue FY 2025-26', ref, private, allowed_doc_ids=ids)
        assert {'infosys-ar-26.pdf', 'TCS_Annual_Report_2025-26.pdf'} <= {h['filename'] for h in hits}
    finally:
        ref.close(); private.close()


def test_permanent_reference_database_is_readonly():
    db = connect_database(DB_PATH, readonly=True)
    try:
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            store_document(db, 'never_store_test', 'never.pdf', 'pdf', 1, 10, [('page 1', 'a'*80)])
        assert len(list_documents(db)) == 4
    finally:
        db.close()


def test_citation_guard_normalizes_brackets_and_filters_sources():
    evidence = [{'id':'S1','filename':'report.pdf','location':'PDF page 3', 'excerpt':'Omega revenue'}]
    validated = validate_generated_citations('Omega revenue was 10 crore【S1】', evidence)
    assert validated['answer'].endswith('[S1]')
    assert validated['sources'] == evidence
    assert validate_generated_citations('Value [s1]', evidence)['answer'].endswith('[S1]')
    rejected = validate_generated_citations('Revenue was 10 crore [S99]', evidence)
    assert rejected == {'answer': INVALID_CITATIONS, 'sources':[]}
    assert validate_generated_citations('Revenue was 10 crore', evidence)['sources'] == []
    assert validate_generated_citations('Revenue was 10 crore', evidence)['answer'] == INVALID_CITATIONS
    assert 'could not' in validate_generated_citations('I could not verify the value.', evidence)['answer']


def test_error_messages_hide_internal_server_details():
    error = ValueError('Unexpected crash; token secret-super-private; internal stack /root/file')
    public = safe_answer_error(error)
    assert 'secret-super-private' not in public and '/root/' not in public
    assert 'logs' in public
    assert 'GROQ_API_KEY' in safe_answer_error(ValueError('GROQ_API_KEY is missing'))


def test_mock_llm_answers_have_only_resolvable_citations(monkeypatch):
    def mock_answer(text):
        def create(**kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
        return SimpleNamespace(Groq=lambda **kwargs: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    db = connect_database()
    try:
        data = b'Project,PrincipalRisk\nOmega,VendorFailureAndContinuity\n'
        item = plan_session_uploads([FakeUpload('omega.csv', data)], []).candidates[0]
        ingest(db, item)
        prompt = 'What is the principal risk for project Omega?'
        monkeypatch.setitem(sys.modules, 'groq', mock_answer('The risk is vendor failure【S1】'))
        good = generate_answer(prompt, None, db, [], 'test-key', 'mock-model')
        assert good['sources'] and good['sources'][0]['id'] == 'S1'
        assert '[S1]' in good['answer']
        monkeypatch.setitem(sys.modules, 'groq', mock_answer('The risk is vendor failure [S55]'))
        bad = generate_answer(prompt, None, db, [], 'test-key', 'mock-model')
        assert bad['answer'] == INVALID_CITATIONS and bad['sources'] == []
    finally:
        db.close()
