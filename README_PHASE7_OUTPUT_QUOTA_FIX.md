# ReportLens AI — Phase 7 Groq output-token quota fix

## Problem
Qwen `qwen/qwen3.8-27b` returned HTTP 429: output tokens per minute (OTPM), limit 1,000, used 954, requested 321. RAGAS `FactualCorrectness` makes multiple underlying LLM requests per question; previous `--delay` only spaced out completed metric scores and could not protect those internal calls.

## Fix
- All RAGAS judge calls now pass through an `httpx.AsyncClient` with `GroqQuotaTransport`.
- The transport observes actual `completion_tokens` usage from API responses, reserves tokens for the next request and throttles requests even within a single RAGAS metric.
- On HTTP 429, it honors Groq's `retry-after` header or parses its `Please try again in ...` message and retries **only that HTTP request**, avoiding restarting successful internal metric calls.
- Very long recovery periods or repeated 429s return control to the existing checkpoint/resume mechanism.
- Existing judge settings/configurations, saved answers, baseline results and RAGAS scores are unchanged.

## Install (PowerShell)

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\ReportLens_AI_Phase7_Groq_Quota_Fix.zip" -DestinationPath "C:\Projects" -Force
cd C:\Projects\reportlens-ai
python -m pytest -q
```

## Continue saved factual correctness checkpoint

```powershell
python -m evaluation.ragas_eval --input evaluation\results_after_fix_rescored\results.json --output-dir evaluation\results_after_fix_rescored\ragas_qwen_factual_contextualized --model qwen/qwen3.8-27b --metrics factual_correctness --reference-mode contextualized --resume --delay 5 --judge-output-tpm 1000 --judge-output-reserve 400 --quota-retries 8
```

The same `judge_settings.json` identity is retained; `--resume` skips successful saved scores, including Q01–Q20 if present. The runner still prints those completed rows as status output. If Q21 is partially scored, it is retried. No new dataset and no reindexing needed.

`Judge quota pacing:` and `Groq 429:` are expected throttling messages, not test failures. The script may take longer than the old runner; don't launch other Groq requests concurrently if possible.

**Caveats:** The transport's 1,000-OTPM budget matches the user's observed Qwen organization limit, but rate limits vary by organization and can change. A judge request that exceeds 1,000 OTPM by itself, or a shared daily quota exhaustion, may still fail. The runner saves the checkpoint and can resume. Quota management does not change or improve correctness scores; inspect low factual-correctness results separately.

## Files replaced/added
- evaluation/ragas_eval.py (replaced, backward compatible)
- evaluation/groq_quota_transport.py (new)
- tests/test_groq_quota_transport.py (new)

**Not touched**: app.py, .env, SQLite index, project requirements, ground truth, saved 35 generated answers, or any results files.
