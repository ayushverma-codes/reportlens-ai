"""Integrity checks for the supplied, immutable 35-question evaluation set."""
import csv
import json
from collections import Counter
from pathlib import Path

import pytest

from src.evaluation.dataset_loader import load_ground_truth

ROOT = Path(__file__).resolve().parents[1] / 'evaluation' / 'ground_truth'
EXPECTED = {'Factual': 8, 'Numerical': 5, 'Comparison': 7,
            'Analysis': 8, 'Summary': 2, 'Unanswerable': 5}
REQUIRED = {'id', 'category', 'question', 'ground_truth_answer',
            'source_document', 'source_section', 'source_page_or_note',
            'expected_behavior'}


def test_missing_ground_truth_is_explicit(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_ground_truth(tmp_path)


def test_ground_truth_count_categories_and_unique_ids():
    rows = load_ground_truth(ROOT)
    assert len(rows) == 35
    assert Counter(row['category'] for row in rows) == EXPECTED
    assert {row['id'] for row in rows} == {f'Q{i:02d}' for i in range(1, 36)}
    assert all(REQUIRED == set(row) and all(str(v).strip() for v in row.values()) for row in rows)


def test_csv_json_match_without_rewriting_ground_truth():
    with (ROOT / 'tcs_rag_ground_truth_35.csv').open(encoding='utf-8-sig', newline='') as handle:
        csv_rows = list(csv.DictReader(handle))
    json_rows = json.loads((ROOT / 'tcs_rag_ground_truth_35.json').read_text(encoding='utf-8'))
    assert csv_rows == json_rows


def test_unanswerable_cases_expect_abstention():
    rows = load_ground_truth(ROOT)
    unanswerable = [row for row in rows if row['category'] == 'Unanswerable']
    assert len(unanswerable) == 5
    assert all(row['expected_behavior'].lower().startswith('abstain') for row in unanswerable)
