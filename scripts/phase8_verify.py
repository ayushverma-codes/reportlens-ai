"""Phase 8 no-network smoke and performance audit.

Run: python -m scripts.phase8_verify
Outputs: phase8/results/metrics.json and phase8/results/PHASE8_REPORT.md
This never calls Groq and never edits permanent report indexes.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
import tracemalloc
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

from src.document_routing import AUTO, catalog, select_docs
from src.fast_rag import (
    DB_PATH, connect_database, content_id, csv_chunks, delete_document,
    generate_answer, list_documents, pdf_chunks, retrieve, store_document,
)
from src.upload_policy import plan_session_uploads


class ExampleUpload:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self.data = data
        self.size = len(data)

    def getvalue(self):
        return self.data


def tiny_pdf(content: str) -> bytes:
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((42, 68), content)
        return pdf.tobytes()


def ms(seconds: float) -> float:
    return round(seconds * 1000, 3)


def benchmark_retrieval(reference, private, count: int = 16) -> dict:
    questions = (
        'What was TCS consolidated revenue in FY 2022-23?',
        'What was TCS consolidated revenue in FY 2023-24?',
        'What was TCS consolidated revenue in FY 2024-25?',
        'What was TCS consolidated revenue in FY 2025-26?',
    )
    samples = []
    observed = 0
    for i in range(count):
        question = questions[i % len(questions)]
        start = time.perf_counter()
        hits = retrieve(question, reference, None, limit=9)
        samples.append(ms(time.perf_counter() - start))
        if not hits:
            raise AssertionError(f'Retrieval returned zero results for: {question}')
        observed += 1
    ordered = sorted(samples)
    return {
        'queries': observed,
        'p50_ms': round(statistics.median(samples), 3),
        'p95_ms_nearest_rank': ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)],
        'min_ms': ordered[0], 'max_ms': ordered[-1],
    }


def run(output_dir: str | Path) -> dict:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    events = []
    tracemalloc.start()
    checks: list[dict] = []

    def check(name: str, condition: bool, notes: str):
        checks.append({'name': name, 'passed': bool(condition), 'details': notes})
        if not condition:
            raise AssertionError(f'Phase 8 verification failed: {name}: {notes}')

    started = time.perf_counter()
    with closing(connect_database(DB_PATH, readonly=True)) as ref, closing(connect_database()) as temp:
        reference_docs = list_documents(ref)
        check('permanent_reports', len(reference_docs) == 4,
              f'Found {len(reference_docs)} permanent reports')
        check('expected_index_chunk_count', sum(d['chunk_count'] for d in reference_docs) > 3000,
              f"{sum(d['chunk_count'] for d in reference_docs)} indexed chunks")
        index_size = DB_PATH.stat().st_size

        pdf_data = tiny_pdf('Infosys revenue from operations for fiscal year 2025-26 is 178650 crore.')
        csv_data = b'Employee,Revenue\nAlpha,150\nBeta,350\n'
        uploads = [ExampleUpload('infosys-ar-26.pdf', pdf_data),
                   ExampleUpload('test-financials.csv', csv_data)]
        plan = plan_session_uploads(uploads, [])
        check('upload_preflight', len(plan.candidates) == 2 and not plan.errors,
              'Two synthetic uploads pass policy')
        pdf_ms = csv_ms = 0.0
        for item in plan.candidates:
            begin = time.perf_counter()
            if item.kind == 'pdf':
                count, chunks = pdf_chunks(item.data)
                pdf_ms = ms(time.perf_counter() - begin)
            else:
                count, chunks = csv_chunks(item.data)
                csv_ms = ms(time.perf_counter() - begin)
            stored = store_document(temp, item.doc_id, item.filename, item.kind,
                                    count, len(item.data), chunks)
            check(f'index_{item.kind}', stored > 0,
                  f'{item.filename}: {count} pages/rows, {stored} chunks')
        check('session_upload_count', len(list_documents(temp)) == 2,
              'Private index contains only two synthetic uploads')
        hits = retrieve('Infosys revenue from operations 2025-26', None, temp)
        check('uploaded_pdf_retrieval',
              any(h['filename'] == 'infosys-ar-26.pdf' for h in hits),
              'Retrieved synthetic private PDF')
        hits_csv = retrieve('Employee Revenue', None, temp)
        check('uploaded_csv_retrieval',
              any('total 500' in h['content'] for h in hits_csv),
              'Retrieved exact aggregate from synthetic CSV')
        groups = catalog(reference_docs, list_documents(temp))
        ids, clarification, company = select_docs('TCS annual revenue', groups, AUTO)
        check('company_selection', not clarification and company == 'TCS',
              'TCS selected exclusively')
        summary = generate_answer('TCS annual revenues', ref, temp, [], '', 'unused',
                                  allowed_doc_ids=ids, company_scope=company)
        check('grounded_local_answer', '2,25,458' in summary['answer'] and summary['sources'],
              'TCS financial overview returns sourced annual figures without Groq')
        ids, clarification, company = select_docs('Compare TCS and Infosys revenue FY 2025-26',
                                                   groups, AUTO)
        check('cross_company_scope', not clarification and len(ids) == 5,
              'Comparison includes four TCS and one Infosys PDF')
        actual = retrieve('Compare TCS and Infosys revenue FY 2025-26', ref, temp,
                          allowed_doc_ids=ids)
        check('cross_company_retrieval',
              {'TCS_Annual_Report_2025-26.pdf', 'infosys-ar-26.pdf'} <=
              {h['filename'] for h in actual},
              'Found evidence for both named companies')
        isolated = connect_database()
        try:
            check('session_isolation', not list_documents(isolated) and
                  not retrieve('Employee Revenue', None, isolated),
                  'A new SQLite session cannot see private uploads')
        finally:
            isolated.close()
        pdf_id = content_id(pdf_data)
        delete_document(temp, pdf_id)
        check('individual_delete',
              not any(h['filename'] == 'infosys-ar-26.pdf'
                      for h in retrieve('Infosys revenue', None, temp)),
              'Deleted PDF absent from the FTS index')
        bench = benchmark_retrieval(ref, temp)

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    result = {
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'python': platform.python_version(), 'platform': platform.system(),
        'status': 'passed',
        'checks_passed': sum(int(c['passed']) for c in checks),
        'checks_total': len(checks), 'checks': checks,
        'reference_report_count': len(reference_docs),
        'reference_index_bytes': index_size,
        'reference_total_pages': sum(d['page_count'] for d in reference_docs),
        'reference_chunk_count': sum(d['chunk_count'] for d in reference_docs),
        'synthetic_pdf_parse_ms': pdf_ms,
        'synthetic_csv_parse_ms': csv_ms,
        'retrieval': bench,
        'python_tracemalloc_peak_mib': round(peak / (1024 * 1024), 3),
        'elapsed_ms': ms(time.perf_counter() - started),
        'groq_latency': None,
        'semantic_embedding_time': None,
    }
    (output / 'metrics.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    details = '\n'.join(
        f"| {c['name']} | {'PASS' if c['passed'] else 'FAIL'} | {c['details']} |"
        for c in checks
    )
    report = f'''# ReportLens AI — Phase 8 Offline Verification

Generated UTC: {result['generated_utc']}  
Platform: {result['platform']} / Python {result['python']}

## Results

**{result['checks_passed']}/{result['checks_total']} checks passed.**

| Check | Status | Notes |
|---|---|---|
{details}

## Resource measurements (local environment; not SLAs)

| Measurement | Value |
|---|---:|
| Permanent reports | {result['reference_report_count']} |
| Indexed pages | {result['reference_total_pages']} |
| Indexed chunks | {result['reference_chunk_count']} |
| Permanent index on disk | {index_size / (1024*1024):.2f} MiB |
| Synthetic 1-page PDF parsing | {pdf_ms} ms |
| Synthetic 2-row CSV parsing | {csv_ms} ms |
| Retrieval median (p50; {bench['queries']} requests) | {bench['p50_ms']} ms |
| Retrieval p95 (nearest-rank) | {bench['p95_ms_nearest_rank']} ms |
| Peak traced Python allocations | {result['python_tracemalloc_peak_mib']} MiB |
| Offline verification runtime | {result['elapsed_ms']} ms |

## Test boundaries / known limitations

- No Groq API calls were made. Live answer latency, LLM correctness and judge behavior were **not measured** here.
- These tests exercise the Python backend, not a real browser, Streamlit Community Cloud or multi-browser concurrency.
- The memory figure is `tracemalloc` Python allocations, **not process RSS** or total native-library memory.
- The retrieval benchmark is an observed local run, not a throughput or production-latency guarantee.
- Scanned PDFs require OCR, which this fast lexical pipeline does not implement.
- SQLite FTS5 provides lexical retrieval; semantic embeddings/ChromaDB are not part of the fast architecture.
- Valid citation IDs do **not** prove that cited text supports each generated claim; separate manual citation audit is required.
- Model output with no resolvable citation is now withheld rather than presented as grounded fact.

## Next gate

Run the full test suite (`python -m pytest -q`) and manually test browser-level upload/removal,
conversation reset, CSV aggregation and cross-company comparison on Windows. Then inspect
`metrics.json` and validate the public deployment separately during Phase 9.
'''
    (output / 'PHASE8_REPORT.md').write_text(report, encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description='Run a no-Groq Phase 8 smoke and performance check')
    parser.add_argument('--output-dir', default='phase8/results')
    args = parser.parse_args()
    try:
        result = run(args.output_dir)
    except Exception as exc:
        print(f'Phase 8 verification FAILED: {type(exc).__name__}: {exc}')
        raise SystemExit(1) from exc
    print(f"Phase 8: {result['checks_passed']}/{result['checks_total']} checks passed")
    print(f"PDF extraction: {result['synthetic_pdf_parse_ms']} ms; CSV extraction: {result['synthetic_csv_parse_ms']} ms")
    print(f"Retrieval p50: {result['retrieval']['p50_ms']} ms; p95: {result['retrieval']['p95_ms_nearest_rank']} ms")
    print(f"Saved: {Path(args.output_dir).resolve()}")


if __name__ == '__main__':
    main()
