"""Phase 7 evaluation regression checks; no Groq network access required."""
from pathlib import Path

import pytest

from evaluation.dataset_loader import load_ground_truth
from evaluation.evaluate import run
from evaluation.metrics import (is_abstention, doc_coverage, value_coverage,
                                cited_source_flags)


def test_ground_truth_integrity():
    cases = load_ground_truth()
    assert len(cases) == 35
    assert cases[0]['id'] == 'Q01' and cases[-1]['id'] == 'Q35'


def test_document_coverage_multi_doc():
    assert doc_coverage('a.pdf; b.pdf', [{'filename':'a.pdf'}, {'filename':'b.pdf'}]) == 1
    assert doc_coverage('a.pdf; b.pdf', [{'filename':'a.pdf'}]) == 0.5
    assert doc_coverage('All four reports', []) is None


def test_number_coverage_indian_commas():
    assert value_coverage('₹225,458 crore.', '₹2,25,458 crore [S1]') == 1.0
    assert value_coverage('₹225,458 crore.', 'Revenue from operations 2,25,458 1,91,754') == 1.0
    assert value_coverage('EBIT ₹66,838 crore, margin 25.0%.', '66,838; 25.0%') == 1
    assert value_coverage('₹225,458 crore.', '₹225,000 crore') == 0


def test_abstention_and_citation_flags():
    assert is_abstention("I couldn't find that fiscal year in the available reports.")
    assert is_abstention('Cannot determine from the uploaded documents.')
    assert not is_abstention('The answer is ₹2,25,458 crore [S1].')
    assert cited_source_flags('₹2,25,458 [S1]', [{'id':'S1'}]) == (True, 1)
    assert cited_source_flags('₹2,25,458 [S9]', [{'id':'S1'}]) == (False, 1)


def test_offline_runner_persists_raw_contexts(tmp_path):
    rows = run(mode='retrieval', directory=tmp_path, top_k=5, model='ignored',
               sleep=0, resume=False, limit=2)
    assert len(rows) == 2
    assert all(r['status'] == 'retrieval_only' for r in rows)
    assert all(r['retrieved_contexts'] and r['retrieval_doc_coverage'] == 1.0 for r in rows)
    for name in ('results.csv','results.json','summary.json','EVALUATION_REPORT.md'):
        assert (tmp_path / name).exists()


def test_full_runner_uses_actual_generate_answer_interface_and_resume(tmp_path, monkeypatch):
    import evaluation.evaluate as evaluation_module
    monkeypatch.setenv('GROQ_API_KEY', 'mock-key')
    questions = load_ground_truth()
    calls = []
    def fake_answer(question, permanent, temporary, messages, api_key, model,
                    allowed_doc_ids=None, company_scope=''):
        calls.append(question)
        assert api_key == 'mock-key'
        return {'answer': questions[len(calls)-1]['ground_truth_answer'] + ' [S1]',
                'sources': [{'id':'S1', 'filename':'annual-report-2022-2023.pdf',
                             'location':'PDF page 191'}]}
    monkeypatch.setattr(evaluation_module, 'generate_answer', fake_answer)
    rows = run(mode='full', directory=tmp_path, top_k=5,
               model='mock-model', sleep=0, resume=False, limit=2)
    assert len(calls) == 2
    assert all(r['status'] == 'answered' for r in rows)
    assert all(r['citation_ids_valid'] is True for r in rows)
    assert all(r['answer_number_coverage'] == 1.0 for r in rows)
    rows_again = run(mode='full', directory=tmp_path, top_k=5,
                     model='mock-model', sleep=0, resume=True, limit=2)
    assert len(calls) == 2 and len(rows_again) == 2


def test_full_runner_requires_credentials(tmp_path, monkeypatch):
    import evaluation.evaluate as evaluation_module

    # The real application intentionally loads GROQ_API_KEY from .env.
    # Disable that loading ONLY for this negative unit test so a local .env
    # cannot restore the key after monkeypatch.delenv().
    monkeypatch.setattr(evaluation_module, 'load_dotenv', lambda *args, **kwargs: False)
    monkeypatch.delenv('GROQ_API_KEY', raising=False)

    with pytest.raises(RuntimeError, match='GROQ_API_KEY'):
        run(mode='full', directory=tmp_path, top_k=5, model='mock',
            sleep=0, resume=False, limit=1)
