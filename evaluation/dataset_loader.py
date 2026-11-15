"""Read and check the ORIGINAL TCS 35-question ground truth without altering it."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GROUND_TRUTH = ROOT / 'ground_truth'
REQUIRED = ('id', 'category', 'question', 'ground_truth_answer', 'source_document',
            'source_section', 'source_page_or_note', 'expected_behavior')
EXPECTED_CATEGORIES = {'Factual': 8, 'Numerical': 5, 'Comparison': 7,
                       'Analysis': 8, 'Summary': 2, 'Unanswerable': 5}


def load_ground_truth(folder: Path | str = GROUND_TRUTH) -> list[dict[str, str]]:
    folder = Path(folder)
    json_path = folder / 'tcs_rag_ground_truth_35.json'
    csv_path = folder / 'tcs_rag_ground_truth_35.csv'
    if not json_path.is_file() or not csv_path.is_file():
        raise FileNotFoundError(f'Both original ground-truth files must exist in {folder}')
    rows = json.loads(json_path.read_text(encoding='utf-8-sig'))
    with csv_path.open(encoding='utf-8-sig', newline='') as file:
        csv_rows = list(csv.DictReader(file))
    if not isinstance(rows, list) or len(rows) != 35 or len(csv_rows) != 35:
        raise ValueError('Expected exactly 35 original questions in BOTH files.')
    for i, (json_row, csv_row) in enumerate(zip(rows, csv_rows), start=1):
        if not isinstance(json_row, dict) or any(k not in json_row for k in REQUIRED):
            raise ValueError(f'Missing required ground-truth fields at row {i}')
        if {k: str(json_row[k]) for k in REQUIRED} != {k: str(csv_row[k]) for k in REQUIRED}:
            raise ValueError(f'CSV/JSON ground truth disagreement at row {i}')
        if json_row['id'] != f'Q{i:02d}':
            raise ValueError(f'Question IDs/order changed at row {i}')
    distribution = Counter(row['category'] for row in rows)
    if dict(distribution) != EXPECTED_CATEGORIES:
        raise ValueError(f'Unexpected category distribution: {distribution}')
    return rows


if __name__ == '__main__':
    data = load_ground_truth()
    print(f'Ground-truth integrity: {len(data)}/35 rows; CSV and JSON exactly agree')
    print('Categories:', EXPECTED_CATEGORIES)
