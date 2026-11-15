"""Phase 7: reproducible offline retrieval / live Groq answer evaluation.

Run from PROJECT ROOT:
  python -m evaluation.evaluate --mode retrieval
  python -m evaluation.evaluate --mode full --resume --sleep 5

Use only the permanent four-report index. Never include private user uploads in
this benchmark: Q34 must remain unanswerable because Infosys is not indexed.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from evaluation.dataset_loader import load_ground_truth
from evaluation.metrics import (aggregate, cited_source_flags, doc_coverage,
                                is_abstention, value_coverage)
from src.document_routing import AUTO, catalog, select_docs
from src.fast_rag import (DB_PATH, connect_database, generate_answer,
                          list_documents, retrieve)

ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT / 'evaluation' / 'results'


def _write_outputs(rows: list[dict], directory: Path, *, mode: str, model: str,
                   top_k: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    items = sorted(rows, key=lambda r: r['id'])
    target = directory / 'results.json'
    temporary = directory / 'results.json.tmp'
    temporary.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(target)

    cols = ('id', 'category', 'question', 'reference', 'answer', 'status',
            'retrieval_doc_coverage', 'evidence_number_coverage',
            'answer_number_coverage', 'citation_ids_valid', 'abstention_correct',
            'retrieved_doc_names', 'retrieved_locations', 'answer_source_locations',
            'expected_source_document', 'expected_page_or_note', 'error')
    with (directory / 'results.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=cols, extrasaction='ignore')
        writer.writeheader()
        for item in items:
            converted = dict(item)
            for key in ('retrieved_doc_names', 'retrieved_locations', 'answer_source_locations'):
                converted[key] = json.dumps(converted.get(key, []), ensure_ascii=False)
            writer.writerow(converted)

    summary = aggregate(items)
    summary.update({'mode': mode, 'production_model': model if mode == 'full' else None,
                    'retrieval_top_k': top_k, 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
                    'warnings': [
                        'Offline retrieval metrics do NOT measure answer correctness or RAGAS.',
                        'Document-level source coverage is not page-level citation accuracy.',
                        'Numeric coverage is a heuristic; human verification of currency, units, FY and page remains necessary.',
                        'The evaluation contains only four TCS reports; Infosys must be absent for Q34.',
                    ]})
    (directory / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = [f'# ReportLens AI — Phase 7 {mode} evaluation', '',
             f'Generated: {summary["timestamp_utc"]}', '',
             f'- Dataset: {len(items)} original TCS benchmark questions',
             f'- Mode: `{mode}`',
             f'- Successfully answered: {summary["answered"]}',
             f'- Retrieval-only cases: {summary["retrieval_only"]}',
             f'- Errors: {summary["error"]}', '',
             '| Category | Cases | Completed | Document coverage@k | Numeric answer coverage | Abstention correct |',
             '|---|---:|---:|---:|---:|---:|']
    def fmt(x):
        return 'not measured' if x is None else f'{x:.1%}'
    for name, s in summary['by_category'].items():
        lines.append(f'| {name} | {s["questions"]} | {s["completed"]} | '
                     f'{fmt(s["retrieval_doc_coverage"])} | {fmt(s["answer_number_coverage"])} | '
                     f'{fmt(s["abstention_correct"])} |')
    lines += ['', '## Interpretation and limitations', '',
              'These are deterministic checks, not RAGAS judge scores.',
              'A hit on a document filename is not evidence of a correct retrieved page or answer.',
              'Numeric answer coverage checks whether reference numbers occur in the response; '
              'it does not validate units, year attribution, or whether supporting pages prove each claim.',
              'Manually audit all financial/citation questions and five abstention questions.',
              'No RAGAS scores are claimed until `evaluation.ragas_eval` runs with an evaluator.', '']
    errors = [r for r in items if r['status'] == 'error']
    if errors:
        lines += ['## Execution errors', '']
        for r in errors:
            lines.append(f'- {r["id"]}: {r.get("error", "Unknown")[:240]}')
    (directory / 'EVALUATION_REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def run(*, mode: str, directory: Path, top_k: int, model: str,
        sleep: float, resume: bool, limit: int | None,
        rerun_ids: set[str] | None = None) -> list[dict]:
    load_dotenv(ROOT / '.env')
    questions = load_ground_truth()
    if not DB_PATH.is_file():
        raise FileNotFoundError(f'Missing permanent report index: {DB_PATH}')
    key = os.getenv('GROQ_API_KEY', '').strip()
    if mode == 'full' and not key:
        raise RuntimeError('GROQ_API_KEY must be configured in .env to run --mode full.')

    existing: dict[str, dict] = {}
    checkpoint = directory / 'results.json'
    if resume and checkpoint.is_file():
        existing = {r['id']: r for r in json.loads(checkpoint.read_text(encoding='utf-8'))}
    if limit is not None:
        questions = questions[:limit]
    if rerun_ids:
        if not resume or not checkpoint.is_file():
            raise ValueError('--rerun-ids requires --resume and an existing results.json checkpoint. '
                             'Copy baseline results to a new output directory first.')
        available = {q['id'] for q in questions}
        invalid = rerun_ids - available
        if invalid:
            raise ValueError('Unknown/filtered evaluation IDs: ' + ', '.join(sorted(invalid)))
        questions = [q for q in questions if q['id'] in rerun_ids]
    # Ensure partial reruns retain all prior completed questions when --resume.
    all_rows = dict(existing)
    with closing(connect_database(DB_PATH, readonly=True)) as permanent:
        docs = list_documents(permanent)
        if len(docs) != 4:
            raise ValueError(f'Benchmark requires exactly four permanent TCS reports; found {len(docs)}')
        if not all('tcs' in d['filename'].lower() or 'annual-report-' in d['filename'].lower()
                   for d in docs):
            raise ValueError('Permanent index includes unexpected documents. This benchmark must be TCS-only.')
        groups = catalog(docs, [])
        if set(groups) != {'TCS'}:
            raise ValueError('Benchmark must contain TCS only, without uploaded Infosys reports.')
        for offset, row in enumerate(questions, 1):
            qid = row['id']
            if resume and qid in existing and not (rerun_ids and qid in rerun_ids) and (
                existing[qid]['status'] == 'answered' or
                mode == 'retrieval' and existing[qid]['status'] == 'retrieval_only'
            ):
                print(f'[{offset}/{len(questions)}] {qid}: already completed; skipping', flush=True)
                continue
            start = time.perf_counter()
            answer = ''
            sources = []
            hits = []
            status, error = 'retrieval_only', ''
            selected_ids, clarification, company = select_docs(row['question'], groups, AUTO, history=[])
            try:
                if clarification:
                    # The same company routing policy as Streamlit; do not claim
                    # a retrieval hit when the app would instead ask clarification.
                    answer = clarification if mode == 'full' else ''
                    status = 'answered' if mode == 'full' else 'retrieval_only'
                else:
                    # Always record the full retriever evidence, even for local
                    # financial shortcuts that skip Groq during generation.
                    hits = retrieve(row['question'], permanent, None,
                                    limit=top_k, allowed_doc_ids=selected_ids)
                    if mode == 'full':
                        output = generate_answer(row['question'], permanent, None, [], key,
                                                 model, allowed_doc_ids=selected_ids,
                                                 company_scope=company)
                        answer = output['answer']
                        sources = output.get('sources', [])
                        status = 'answered'
            except Exception as exc:
                status = 'error'
                error = f'{type(exc).__name__}: {exc}'[:400]

            citations_ok, citation_count = cited_source_flags(answer, sources)
            unanswerable = row['category'] == 'Unanswerable'
            evaluation = {
                'id': qid, 'category': row['category'], 'question': row['question'],
                'reference': row['ground_truth_answer'],
                'expected_source_document': row['source_document'],
                'expected_page_or_note': row['source_page_or_note'],
                'answer': answer, 'answer_sources': sources,
                'retrieved_contexts': [h['content'] for h in hits],
                'retrieved_hits': [dict(filename=h['filename'], location=h['location'],
                                        doc_id=h['doc_id'], score=h.get('score')) for h in hits],
                'retrieved_doc_names': [h['filename'] for h in hits],
                'retrieved_locations': [f"{h['filename']}: {h['location']}" for h in hits],
                'answer_source_locations': [f"{s['filename']}: {s['location']}" for s in sources],
                'retrieval_doc_coverage': None if unanswerable else doc_coverage(row['source_document'], hits),
                'evidence_number_coverage': None if unanswerable else value_coverage(row['ground_truth_answer'],
                                                      '\n'.join(h['content'] for h in hits)),
                'answer_number_coverage': None if unanswerable or status != 'answered'
                                         else value_coverage(row['ground_truth_answer'], answer),
                'citation_ids_valid': citations_ok if status == 'answered' and not unanswerable else None,
                'citation_count': citation_count,
                'abstention_correct': (is_abstention(answer) if status == 'answered' else None)
                                      if unanswerable else None,
                'status': status, 'error': error,
                'elapsed_seconds': round(time.perf_counter() - start, 3),
            }
            all_rows[qid] = evaluation
            _write_outputs(list(all_rows.values()), directory, mode=mode, model=model, top_k=top_k)
            print(f'[{offset}/{len(questions)}] {qid} {row["category"]}: {status} | '
                  f'doc_coverage={evaluation["retrieval_doc_coverage"]} | '
                  f'answer_numbers={evaluation["answer_number_coverage"]} | '
                  f'abstained={evaluation["abstention_correct"]}', flush=True)
            if status == 'error':
                print('  Error:', error, file=sys.stderr)
                # Fail fast on rate limit; partial results have already been saved.
                if 'RateLimitError' in error or '429' in error:
                    print('Rate limited: run again with --resume after quota is available.', file=sys.stderr)
                    break
            if mode == 'full' and sleep and offset < len(questions):
                time.sleep(sleep)
    return list(all_rows.values())


def main():
    load_dotenv(ROOT / '.env')
    parser = argparse.ArgumentParser(description='Evaluate permanent TCS reports on original 35 QA cases')
    parser.add_argument('--mode', choices=['retrieval', 'full'], default='retrieval')
    parser.add_argument('--output-dir', type=Path, default=RESULT_DIR)
    parser.add_argument('--top-k', type=int, default=9)
    parser.add_argument('--model', default=os.getenv('GROQ_MODEL', 'openai/gpt-oss-20b'))
    parser.add_argument('--sleep', type=float, default=5.0,
                        help='Seconds between Groq requests; 429 may still occur.')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--limit', type=int, default=None, help='For local smoke checks; omit for full 35')
    parser.add_argument('--rerun-ids', default='',
                        help='Comma-separated IDs to reevaluate with --resume; preserves other checkpoint rows')
    args = parser.parse_args()
    if args.top_k < 1 or args.top_k > 30:
        parser.error('--top-k must be between 1 and 30')
    try:
        redo_ids = {q.strip().upper() for q in args.rerun_ids.split(',') if q.strip()} or None
        rows = run(mode=args.mode, directory=args.output_dir, top_k=args.top_k,
                   model=args.model, sleep=args.sleep, resume=args.resume, limit=args.limit,
                   rerun_ids=redo_ids)
        print('Saved:', args.output_dir.resolve())
        print('Summary:', json.dumps(aggregate(rows), indent=2))
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        parser.exit(2, f'Evaluation setup error: {exc}\n')


if __name__ == '__main__':
    main()
