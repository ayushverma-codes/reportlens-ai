"""RAGAS judge regression tests without installing RAGAS or calling Groq."""
from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace

import pytest

from evaluation import ragas_eval
from evaluation.judge_preprocessing import contextual_reference, limited_contexts


def _row():
    return {
        'id': 'Q01', 'category': 'Factual', 'status': 'answered',
        'question': 'What was TCS consolidated revenue from operations in FY 2022-23?',
        'reference': '₹225,458 crore.',
        'answer': 'TCS revenue was **₹2,25,458 crore**【S1】【S8】',
        'retrieved_contexts': ['Profit and loss statement: revenue 225458',
                               'Management overview: revenue 225458',
                               'Irrelevant long report section'],
    }


def test_reference_mode_original_is_bit_for_bit_unchanged():
    r = _row()
    kw = ragas_eval._metric_kwargs('factual_correctness', r)
    assert kw == {'response': r['answer'], 'reference': r['reference']}
    assert r['reference'] == '₹225,458 crore.'


def test_question_aware_reference_is_transparent_and_does_not_mutate_saved_row():
    r = _row()
    kw = ragas_eval._metric_kwargs('factual_correctness', r,
                                   reference_mode='contextualized')
    assert kw['reference'] == ('TCS consolidated revenue from operations in FY '
                               '2022-23 was ₹225,458 crore.')
    assert kw['response'] == 'TCS revenue was ₹2,25,458 crore'
    assert r['reference'] == '₹225,458 crore.'
    assert r['answer'].endswith('【S1】【S8】')


def test_complex_narrative_reference_not_rewritten():
    reference = 'TCS cited modernization and outsourcing.'
    assert contextual_reference('What changed over the year?', reference) == reference


def test_context_limits_preserve_order_and_original():
    r = _row()
    kw = ragas_eval._metric_kwargs('faithfulness', r,
                                   max_contexts=2, max_context_chars=12)
    assert kw['retrieved_contexts'] == ['Profit and l', 'Management o']
    assert len(r['retrieved_contexts']) == 3
    assert len(r['retrieved_contexts'][0]) > 12
    with pytest.raises(ValueError):
        limited_contexts(r['retrieved_contexts'], max_contexts=-1)


def _mock_ragas(monkeypatch, scorer):
    monkeypatch.setitem(sys.modules, 'ragas', SimpleNamespace(__version__='0.4.4'))
    monkeypatch.setattr(ragas_eval, '_init_judge', lambda *a, **k: 'mock-judge')
    monkeypatch.setattr(ragas_eval, '_make_metric', lambda name, judge: scorer)


def _run_once(path, directory, *, resume=False, reference_mode='contextualized',
              max_contexts=0, scorer_fallback=None):
    return asyncio.run(ragas_eval.run(
        path, directory, 'qwen/qwen3.8-27b', 'fake-key',
        'https://api.groq.com/openai/v1', ['factual_correctness'], 1, 0,
        resume, reference_mode=reference_mode, max_contexts=max_contexts))


def test_saves_judge_settings_and_uses_contextualized_reference(tmp_path, monkeypatch):
    row = _row()
    inp = tmp_path / 'input.json'
    inp.write_text(json.dumps([row], ensure_ascii=False), encoding='utf-8')
    calls = []
    class Scorer:
        async def ascore(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(value=1.0)
    _mock_ragas(monkeypatch, Scorer())
    dest = tmp_path / 'out'
    _run_once(inp, dest)
    assert len(calls) == 1
    assert calls[0]['reference'].endswith('was ₹225,458 crore.')
    assert json.loads((dest / 'ragas_scores.json').read_text())[0]['factual_correctness'] == 1
    settings = json.loads((dest / 'judge_settings.json').read_text())
    assert settings['judge_model'] == 'qwen/qwen3.8-27b'
    assert settings['reference_mode'] == 'contextualized'
    _run_once(inp, dest, resume=True)
    assert len(calls) == 1  # Resume does not re-charge for already completed scores
    with pytest.raises(RuntimeError, match='settings differ'):
        _run_once(inp, dest, resume=True, max_contexts=2)


def test_stops_after_429_and_resume_succeeds(tmp_path, monkeypatch):
    inp = tmp_path / 'in.json'
    inp.write_text(json.dumps([_row()], ensure_ascii=False), encoding='utf-8')
    class Limited:
        async def ascore(self, **kwargs):
            raise RuntimeError('Error code: 429 rate limit')
    _mock_ragas(monkeypatch, Limited())
    dest = tmp_path / 'rate_limited'
    _run_once(inp, dest)
    stalled = json.loads((dest / 'ragas_scores.json').read_text())
    assert stalled[0]['factual_correctness'] is None
    assert '429' in stalled[0]['errors']['factual_correctness']

    class Recovered:
        async def ascore(self, **kwargs):
            return SimpleNamespace(value=0.75)
    _mock_ragas(monkeypatch, Recovered())
    _run_once(inp, dest, resume=True)
    scored = json.loads((dest / 'ragas_scores.json').read_text())
    assert scored[0]['factual_correctness'] == 0.75
    assert scored[0]['errors'] == {}


def test_refuses_resume_without_settings_to_avoid_cross_judge_mixing(tmp_path, monkeypatch):
    inp = tmp_path / 'input.json'
    inp.write_text(json.dumps([_row()], ensure_ascii=False), encoding='utf-8')
    dest = tmp_path / 'legacy'
    dest.mkdir()
    (dest / 'ragas_scores.json').write_text('[]', encoding='utf-8')
    _mock_ragas(monkeypatch, None)
    with pytest.raises(RuntimeError, match='legacy scores'):
        _run_once(inp, dest, resume=True)
