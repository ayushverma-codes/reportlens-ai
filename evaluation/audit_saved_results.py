"""Read-only Phase 7 diagnostic audit; never mutates the saved live results.

Usage:
    python -m evaluation.audit_saved_results
    python -m evaluation.audit_saved_results --input results.json

ID/format diagnostics are not proof that a cited page supports a claim.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

from evaluation.metrics import CITATION_RE

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / 'evaluation' / 'results' / 'results.json'
DEFAULT_OUTPUT = ROOT / 'evaluation' / 'results' / 'audit'

# Recorded questions that require manual or targeted follow-up. These labels
# are for the diagnostic REPORT ONLY, never inserted into application logic.
HUMAN_REVIEW = {
    'Q12': 'Wrong constant-currency growth: 6.0% instead of a 2.4% decline',
    'Q15': 'Truncated FY2025 revenue and incorrect revenue-change arithmetic',
    'Q18': 'Wrong BFSI segment revenue; unrelated/standalone figure used',
    'Q19': 'Wrong industry-vertical growth rate; standalone values used',
    'Q21': 'Unsupported or misleading currency-impact and exceptional-expense explanations',
    'Q22': 'Misses cost optimisation, vendor consolidation, and modernisation priorities',
    'Q28': 'Document-listing intent hijacked a financial-controls question',
    'Q30': 'Manufacturing omitted from the industry cluster list',
    'Q32': 'Calendar-year question answered with fiscal-year profit table',
}


def audit_rows(rows: list[dict]) -> tuple[list[dict], dict]:
    details = []
    for row in rows:
        answer = row.get('answer', '')
        refs = CITATION_RE.findall(answer)
        candidate_sources = row.get('retrieved_hits', [])
        ids_in_range = bool(refs) and all(
            1 <= int(ref[1:]) <= len(candidate_sources) for ref in refs
        )
        declared = {s.get('id') for s in row.get('answer_sources', [])}
        validated_declared = bool(refs) and all(ref in declared for ref in refs)
        inferred = []
        for ref in dict.fromkeys(refs):
            index = int(ref[1:]) - 1
            if 0 <= index < len(candidate_sources):
                hit = candidate_sources[index]
                inferred.append({'citation': ref, 'filename': hit.get('filename'),
                                 'location': hit.get('location')})
        details.append({
            'id': row['id'], 'category': row['category'],
            'status': row.get('status'),
            'document_coverage': row.get('retrieval_doc_coverage'),
            'numeric_answer_coverage': row.get('answer_number_coverage'),
            'abstention_correct': row.get('abstention_correct'),
            'bracketed_citation_count': len(refs),
            'citation_ids_in_retrieved_topk': ids_in_range,
            'citation_ids_in_recorded_source_list': validated_declared,
            'inferred_topk_citation_targets': inferred,
            'manual_review_reason': HUMAN_REVIEW.get(row['id'], ''),
        })
    answerable = [r for r in details if r['category'] != 'Unanswerable']
    unanswerable = [r for r in details if r['category'] == 'Unanswerable']
    summary = {
        'questions': len(rows),
        'answerable': len(answerable),
        'unanswerable': len(unanswerable),
        'citation_ids_in_retrieved_topk': sum(r['citation_ids_in_retrieved_topk'] for r in answerable),
        'citation_ids_in_recorded_sources': sum(r['citation_ids_in_recorded_source_list'] for r in answerable),
        'abstention_correct_count': sum(r['abstention_correct'] is True for r in unanswerable),
        'flagged_for_manual_review': sorted(HUMAN_REVIEW),
        'important_qualifications': [
            'An inferred S-number mapping is positional and has NOT been checked for source support.',
            'The original stored answer_sources arrays may be empty because Groq used 【S1】 citations.',
            'Numeric coverage checks text presence, not units, fiscal year, or financial consistency.',
            'The original results are not overwritten or rescored by this script.',
        ],
    }
    return details, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=DEFAULT_INPUT)
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    rows = json.loads(args.input.read_text(encoding='utf-8'))
    details, summary = audit_rows(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / 'audit_summary.json').write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    (args.output_dir / 'audit_details.json').write_text(
        json.dumps(details, indent=2, ensure_ascii=False), encoding='utf-8')
    with (args.output_dir / 'audit_details.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        columns = [key for key in details[0] if key != 'inferred_topk_citation_targets']
        writer = csv.DictWriter(stream, columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(details)
    report = [
        '# ReportLens AI — Phase 7 Saved-Results Audit', '',
        f'- Analyzed saved answers: **{summary["questions"]}**',
        f'- Answerable / unanswerable: **{len(answerable := [r for r in details if r["category"] != "Unanswerable"])} / {summary["unanswerable"]}**',
        f'- Bracketed citation IDs within retrieved top-k: **{summary["citation_ids_in_retrieved_topk"]}/{summary["answerable"]}** (ID coverage only)',
        f'- Citation IDs validated against stored `answer_sources`: **{summary["citation_ids_in_recorded_sources"]}/{summary["answerable"]}**',
        f'- Correct abstentions: **{summary["abstention_correct_count"]}/{summary["unanswerable"]}**',
        '', '## Findings requiring review', '',
        '| Question | Finding |', '|---|---|',
    ]
    for q, reason in HUMAN_REVIEW.items():
        report.append(f'| {q} | {reason} |')
    report += [
        '', '## Interpretation', '',
        'The citation reader recognizes `[S1]`, `[ S1 ]`, and `【S1】`. '
        'A bracketed citation that maps to one of nine retrieved results is **not** necessarily accurate '
        'or claim-supporting; it only identifies a candidate evidence location.', '',
        'The audit never overwrites `results.json` or the original reference answers.',
        'No RAGAS judge scores have been generated.', '',
    ]
    (args.output_dir / 'AUDIT_REPORT.md').write_text('\n'.join(report), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    print('Wrote:', args.output_dir.resolve())


if __name__ == '__main__':
    main()
