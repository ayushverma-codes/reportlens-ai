"""Recompute deterministic checkpoint metrics WITHOUT invoking Groq or changing answers.

Usage (from project root)::

    python -m evaluation.rescore_saved_results \
        --input evaluation/results_after_fix/results.json \
        --output-dir evaluation/results_after_fix_rescored

This command does not change your original checkpoint or the input JSON file.
It does NOT infer a valid citation source from a positional S-number. Missing
``answer_sources`` remain missing; a cited PDF page is not automatically valid.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from evaluation.evaluate import _write_outputs
from evaluation.metrics import aggregate, cited_source_flags, is_abstention


def rescore_records(saved: list[dict]) -> list[dict]:
    """Recompute checks that are determinable from saved answers and sources."""
    rows = copy.deepcopy(saved)
    for row in rows:
        if row.get('status') != 'answered':
            continue
        if row.get('category') == 'Unanswerable':
            row['abstention_correct'] = is_abstention(row.get('answer', ''))
            row['citation_ids_valid'] = None
        else:
            valid, count = cited_source_flags(
                row.get('answer', ''), row.get('answer_sources', [])
            )
            row['citation_ids_valid'] = valid
            row['citation_count'] = count
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True,
                        help='Saved 35-question results.json to rescore')
    parser.add_argument('--output-dir', type=Path, required=True,
                        help='New directory; must not contain an existing results.json')
    args = parser.parse_args()
    input_file = args.input.resolve()
    output = args.output_dir.resolve()
    if not input_file.is_file():
        parser.error(f'Input checkpoint does not exist: {input_file}')
    if (output / 'results.json').exists():
        parser.error('Output already contains results.json; choose a fresh directory to protect saved results.')
    raw = json.loads(input_file.read_text(encoding='utf-8'))
    if not isinstance(raw, list) or not all(isinstance(r, dict) for r in raw):
        parser.error('Input must be a list of evaluation records.')
    if len({r.get('id') for r in raw}) != len(raw):
        parser.error('Input contains duplicate question IDs.')
    rows = rescore_records(raw)
    previous_summary_file = input_file.parent / 'summary.json'
    metadata = (json.loads(previous_summary_file.read_text(encoding='utf-8'))
                if previous_summary_file.is_file() else {})
    _write_outputs(rows, output, mode=metadata.get('mode', 'full'),
                   model=metadata.get('production_model') or 'not recorded',
                   top_k=metadata.get('retrieval_top_k') or 9)
    changes = []
    for old, new in zip(raw, rows):
        for field in ('abstention_correct', 'citation_ids_valid', 'citation_count'):
            if old.get(field) != new.get(field):
                changes.append((old['id'], field, old.get(field), new.get(field)))
    summary = aggregate(rows)
    note = [
        '# Deterministic rescore of saved Phase 7 checkpoint', '',
        f'Input: `{input_file}`', '',
        'No Groq calls. No answer text, reference answers, retrieved hits, '
        'or source lists were changed.', '',
        '| Question | Metric | Old | Recomputed |',
        '|---|---|---|---|',
    ]
    for qid, name, before, after in changes:
        note.append(f'| {qid} | {name} | {before} | {after} |')
    if not changes:
        note.append('| — | No changes | — | — |')
    note += ['', '## Qualifications', '',
             'A citation ID is only counted as valid if it is present in the '
             'stored `answer_sources` list. Citation correctness and claim '
             'support are NOT measured here.',
             'Previous source lists that were empty remain empty. Recompute '
             'those answers with the fixed app if complete citation metadata is required.',
             'Numerical coverage is a text-matching heuristic, not audited '
             'financial answer accuracy.',
             'The output is a re-score of a checkpoint that may contain both '
             'before- and after-fix answers.', '']
    (output / 'RESCORE_NOTES.md').write_text('\n'.join(note), encoding='utf-8')
    print(f'Saved rescored checkpoint: {output}')
    print(f'Changed scoring fields: {len(changes)}')
    print('Abstention score:', summary['by_category'].get('Unanswerable', {}).get('abstention_correct'))
    for qid, name, before, after in changes:
        print(f'  {qid} {name}: {before} -> {after}')


if __name__ == '__main__':
    main()
