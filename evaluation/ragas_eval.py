"""Optional RAGAS v0.4.x evaluation of saved ReportLens AI answers.

Use an independent judge and save the judge inputs/configuration for transparency.
The original ground truth, model answers, and retrieval results are never modified.

Examples:
 python -m evaluation.ragas_eval --model qwen/qwen3.8-27b --metrics factual_correctness --reference-mode contextualized --limit 2
 python -m evaluation.ragas_eval --model qwen/qwen3.8-27b --metrics faithfulness --max-contexts 2 --max-context-chars 2000 --limit 2
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from dotenv import load_dotenv

from evaluation.judge_preprocessing import (
    clean_for_judge, contextual_reference, limited_contexts,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILE = ROOT / 'evaluation' / 'results' / 'results.json'
AVAILABLE = ('faithfulness', 'context_precision', 'context_recall',
             'factual_correctness', 'answer_correctness', 'answer_relevancy')


def _init_judge(model: str, api_key: str, api_base: str, *,
                output_tpm: int = 1000, output_reserve: int = 400,
                max_429_retries: int = 8):
    import httpx
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from evaluation.groq_quota_transport import GroqQuotaTransport

    # IMPORTANT: A RAGAS factual-correctness score may make multiple calls.
    # Rate-limit at the underlying HTTP request level, not between scores.
    http_client = httpx.AsyncClient(transport=GroqQuotaTransport(
        output_tpm=output_tpm, reserve=output_reserve,
        max_429_retries=max_429_retries), timeout=240)
    client = AsyncOpenAI(api_key=api_key, base_url=api_base,
                         http_client=http_client, max_retries=0, timeout=240)
    return llm_factory(model, provider='openai', client=client)


def _openai_eval_embeddings():
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        raise ValueError('This metric needs OPENAI_API_KEY for embeddings; omit it otherwise.')
    from ragas.embeddings.base import embedding_factory
    from openai import AsyncOpenAI
    return embedding_factory('openai', model='text-embedding-3-small',
                             client=AsyncOpenAI(api_key=key))


def _make_metric(name: str, judge):
    from ragas.metrics.collections import (
        Faithfulness, ContextPrecisionWithReference, ContextRecall,
        FactualCorrectness, AnswerCorrectness, AnswerRelevancy)
    if name == 'faithfulness':
        return Faithfulness(llm=judge)
    if name == 'context_precision':
        return ContextPrecisionWithReference(llm=judge)
    if name == 'context_recall':
        return ContextRecall(llm=judge)
    if name == 'factual_correctness':
        return FactualCorrectness(llm=judge)
    if name == 'answer_correctness':
        return AnswerCorrectness(llm=judge, embeddings=_openai_eval_embeddings())
    if name == 'answer_relevancy':
        return AnswerRelevancy(llm=judge, embeddings=_openai_eval_embeddings())
    raise ValueError(f'Unknown RAGAS metric: {name}')


def _metric_kwargs(name: str, row: dict, reference_mode: str = 'original',
                   max_contexts: int = 0, max_context_chars: int = 0):
    """Provide RAGAS inputs, preserving original saved reference/answer fields."""
    if reference_mode not in ('original', 'contextualized'):
        raise ValueError(f'Unknown reference mode: {reference_mode}')
    reference = row['reference']
    response = row['answer']
    if reference_mode == 'contextualized':
        # This is the SAME transformation used in the successful Q01 diagnostic.
        # It applies to simple numeric 'What was/were ...?' questions only.
        reference = contextual_reference(row['question'], reference)
        response = clean_for_judge(response)
    base = {
        'user_input': row['question'],
        'response': response,
        'retrieved_contexts': limited_contexts(row.get('retrieved_contexts', []),
                                                max_contexts, max_context_chars),
        'reference': reference,
    }
    if name == 'faithfulness':
        keys = ('user_input', 'response', 'retrieved_contexts')
    elif name in ('context_precision', 'context_recall'):
        keys = ('user_input', 'reference', 'retrieved_contexts')
    elif name == 'factual_correctness':
        keys = ('response', 'reference')
    elif name == 'answer_correctness':
        keys = ('user_input', 'response', 'reference')
    elif name == 'answer_relevancy':
        keys = ('user_input', 'response')
    else:
        raise ValueError(name)
    return {k: base[k] for k in keys}


def _save(rows: list[dict], target: Path, model: str, metrics: list[str],
          settings: dict | None = None):
    target.mkdir(parents=True, exist_ok=True)
    if settings is not None:
        (target / 'judge_settings.json').write_text(
            json.dumps(settings, indent=2, ensure_ascii=False), encoding='utf-8')
    (target / 'ragas_scores.json').write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')
    columns = ['id', 'category'] + list(metrics) + ['errors']
    with (target / 'ragas_scores.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            record = dict(row)
            record['errors'] = json.dumps(row.get('errors', {}), ensure_ascii=False)
            writer.writerow(record)
    lines = ['# RAGAS Judge Evaluation', '',
             f'Generated (UTC): {datetime.now(timezone.utc).isoformat()}',
             f'Judge model: `{model}`', '',
             'Only answerable, fully generated responses were judged. The five unanswerable',
             'questions are assessed separately using explicit abstention checks.', '',
             '| Metric | Successful cases | Average |', '|---|---:|---:|']
    for m in metrics:
        valid = [r[m] for r in rows if isinstance(r.get(m), (float, int))]
        lines.append(f'| {m} | {len(valid)} | {mean(valid):.3f} |' if valid
                     else f'| {m} | 0 | not available |')
    if settings:
        lines += ['', 'Judge input configuration:',
                  f"- Reference mode: `{settings['reference_mode']}`",
                  f"- Max contexts: {settings['max_contexts'] or 'unlimited'}",
                  f"- Max characters per context: {settings['max_context_chars'] or 'unlimited'}",
                  '- Context limits can alter faithfulness; original saved retrieval was not changed.']
    lines += ['', 'Judge scores can vary and do not replace audited facts, units or citations.',
              'Errors are saved per case; an unscored metric has no numeric result.']
    (target / 'RAGAS_REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


async def run(input_file: Path, output_dir: Path, model: str, api_key: str,
              api_base: str, metrics: list[str], limit: int | None,
              delay: float, resume: bool, reference_mode: str = 'original',
              max_contexts: int = 0, max_context_chars: int = 0,
              stop_on_rate_limit: bool = True, output_tpm: int = 1000,
              output_reserve: int = 400, max_429_retries: int = 8):
    try:
        import ragas
        version = tuple(int(x) for x in ragas.__version__.split('.')[:2])
        if version != (0, 4):
            raise RuntimeError(f'Expected RAGAS 0.4.x, found {ragas.__version__}.')
    except ImportError as exc:
        raise RuntimeError('Install optional dependencies: '
                           'pip install "ragas>=0.4.4,<0.5" "openai>=1.82,<3"') from exc

    if reference_mode not in ('original', 'contextualized'):
        raise ValueError('reference_mode must be original or contextualized')
    if max_contexts < 0 or max_context_chars < 0:
        raise ValueError('Context limits must be >= 0 (0 means unlimited)')
    rows = json.loads(input_file.read_text(encoding='utf-8'))
    eligible = [r for r in rows if r.get('status') == 'answered'
                and r.get('category') != 'Unanswerable' and r.get('answer')]
    if not eligible:
        raise RuntimeError('No completed live answers. Run the full evaluation first.')
    if limit:
        eligible = eligible[:limit]

    output_json = output_dir / 'ragas_scores.json'
    settings_path = output_dir / 'judge_settings.json'
    settings = {'judge_model': model, 'metrics': metrics,
                'reference_mode': reference_mode,
                'max_contexts': max_contexts,
                'max_context_chars': max_context_chars}
    saved = {}
    if resume and output_json.is_file():
        if not settings_path.is_file():
            raise RuntimeError('Cannot safely resume legacy scores lacking judge_settings.json. '
                               'Use a new --output-dir to avoid mixing judge configurations.')
        previous_settings = json.loads(settings_path.read_text(encoding='utf-8'))
        if previous_settings != settings:
            raise RuntimeError('Saved judge settings differ. '
                               'Use the original settings or a new --output-dir.')
        saved = {r['id']: r for r in json.loads(output_json.read_text(encoding='utf-8'))}
    elif output_json.is_file():
        raise RuntimeError('Output directory already has RAGAS scores. '
                           'Use --resume with matching settings or choose a new --output-dir.')

    judge = _init_judge(model, api_key, api_base,
                        output_tpm=output_tpm, output_reserve=output_reserve,
                        max_429_retries=max_429_retries)
    scorers = {}
    for name in metrics:
        try:
            scorers[name] = _make_metric(name, judge)
        except Exception as exc:
            print(f'Could not initialize {name}: {type(exc).__name__}: {exc}')
    if not scorers:
        raise RuntimeError('No RAGAS metrics initialized.')

    for i, row in enumerate(eligible, 1):
        entry = saved.get(row['id'], {'id': row['id'], 'category': row['category'], 'errors': {}})
        for name, scorer in scorers.items():
            if resume and isinstance(entry.get(name), (int, float)):
                continue
            rate_limited = False
            try:
                result = await scorer.ascore(**_metric_kwargs(
                    name, row, reference_mode=reference_mode,
                    max_contexts=max_contexts, max_context_chars=max_context_chars))
                entry[name] = float(result.value)
                entry['errors'].pop(name, None)
            except Exception as exc:
                entry[name] = None
                entry['errors'][name] = f'{type(exc).__name__}: {exc}'[:300]
                rate_limited = '429' in str(exc) or 'rate limit' in str(exc).lower()
            saved[row['id']] = entry
            _save(list(saved.values()), output_dir, model, metrics, settings)
            if rate_limited and stop_on_rate_limit:
                print('Rate limit encountered; checkpoint saved. '
                      'Rerun with --resume after the reported recovery interval.', flush=True)
                return
            if delay:
                await asyncio.sleep(delay)
        print(f'[{i}/{len(eligible)}] {row["id"]}: ' +
              ', '.join(f'{m}={entry.get(m)}' for m in metrics), flush=True)
    _save(list(saved.values()), output_dir, model, metrics, settings)


def main():
    load_dotenv(ROOT / '.env')
    parser = argparse.ArgumentParser(description='Optional RAGAS 0.4 judge for saved answers')
    parser.add_argument('--input', type=Path, default=DEFAULT_FILE)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'evaluation' / 'results')
    parser.add_argument('--model', default=os.getenv('RAGAS_EVAL_MODEL', 'openai/gpt-oss-20b'))
    parser.add_argument('--base-url', default=os.getenv('RAGAS_EVAL_BASE_URL', 'https://api.groq.com/openai/v1'))
    parser.add_argument('--metrics', default='faithfulness,context_precision,context_recall,factual_correctness')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--delay', type=float, default=4)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--reference-mode', choices=['original', 'contextualized'],
                        default='original', help='Use question-aware references for short numeric answers')
    parser.add_argument('--max-contexts', type=int, default=0,
                        help='Use only first N retrieved chunks for judge; 0 means unlimited')
    parser.add_argument('--max-context-chars', type=int, default=0,
                        help='Trim each judge chunk to N characters; 0 means unlimited')
    parser.add_argument('--keep-going-on-429', action='store_true',
                        help='Continue scoring after a quota error (not recommended)')
    parser.add_argument('--judge-output-tpm', type=int, default=1000,
                        help='Groq output tokens/minute cap (your current Qwen limit: 1000)')
    parser.add_argument('--judge-output-reserve', type=int, default=400,
                        help='Output tokens reserved for the next judge API request')
    parser.add_argument('--quota-retries', type=int, default=8,
                        help='Retries for individual underlying judge API requests')
    args = parser.parse_args()
    names = [part.strip() for part in args.metrics.split(',') if part.strip()]
    if not names or any(m not in AVAILABLE for m in names):
        parser.error('Available metric names: ' + ', '.join(AVAILABLE))
    key = os.getenv('RAGAS_EVAL_API_KEY') or os.getenv('GROQ_API_KEY')
    if not key:
        parser.error('RAGAS_EVAL_API_KEY or GROQ_API_KEY must be set in .env')
    asyncio.run(run(args.input, args.output_dir, args.model, key,
                    args.base_url, names, args.limit, args.delay, args.resume,
                    reference_mode=args.reference_mode, max_contexts=args.max_contexts,
                    max_context_chars=args.max_context_chars,
                    stop_on_rate_limit=not args.keep_going_on_429,
                    output_tpm=args.judge_output_tpm,
                    output_reserve=args.judge_output_reserve,
                    max_429_retries=args.quota_retries))


if __name__ == '__main__':
    main()
