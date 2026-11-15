"""Regression tests: evaluator wording and read-only checkpoint rescore."""
from copy import deepcopy

from evaluation.metrics import is_abstention, cited_source_flags
from evaluation.rescore_saved_results import rescore_records


def test_calendar_year_refusal_is_an_abstention():
    answer = ('I could not verify a calendar-year figure from the available '
              'financial-year reports. Those reports use financial years, '
              'which cannot be substituted for a calendar year.')
    assert is_abstention(answer)
    assert is_abstention("I couldn't find that fiscal year in the available reports.")
    assert is_abstention('Cannot determine from the uploaded documents.')
    assert not is_abstention('The reported net profit was ₹42,303 crore [S1].')


def test_rescore_does_not_modify_answers_or_invent_missing_sources():
    saved = [
        {'id': 'Q01', 'category': 'Factual', 'status': 'answered',
         'answer': 'Revenue was ₹225,458 crore【S1】', 'answer_sources': [],
         'retrieved_hits': [{'filename': 'x.pdf', 'location': 'PDF page 1'}],
         'citation_ids_valid': False, 'citation_count': 0},
        {'id': 'Q32', 'category': 'Unanswerable', 'status': 'answered',
         'answer': 'I could not verify a calendar-year figure from the reports.',
         'answer_sources': [], 'abstention_correct': False},
    ]
    original = deepcopy(saved)
    rows = rescore_records(saved)
    assert saved == original
    assert rows[0]['answer'] == saved[0]['answer']
    assert rows[0]['answer_sources'] == []
    assert rows[0]['citation_ids_valid'] is False
    assert rows[0]['citation_count'] == 1
    assert rows[1]['abstention_correct'] is True


def test_existing_citation_sources_are_checked_normally():
    saved = [{'id': 'Q30', 'category': 'Summary', 'status': 'answered',
              'answer': 'Manufacturing is listed【S1】',
              'answer_sources': [{'id': 'S1', 'filename': 'x.pdf'}],
              'citation_ids_valid': False}]
    rows = rescore_records(saved)
    assert rows[0]['citation_ids_valid'] is True
    assert rows[0]['citation_count'] == 1
    assert cited_source_flags('【S9】', [{'id': 'S1'}]) == (False, 1)
