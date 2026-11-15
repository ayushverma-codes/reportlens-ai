# ReportLens AI — RAGAS Qwen low-quota evaluation patch

## Problem

`qwen/qwen3.8-27b` scored **1.0** for Q01 when the reference was contextualized, but running faithfulness and factual correctness together with nine long PDF passages hit Groq's **7,000 input tokens/minute** limit (6,134 requested while 1,484 already counted).

This patch changes **only offline evaluation**, not `app.py`, financial extraction, the SQLite index, `.env`, ground truth, or saved model answers.

## Changes

- `--reference-mode contextualized` opt-in: for simple numeric "What was/were ...?" questions, use the question subject + unchanged reference number in the judge input. No ground-truth or answer files are rewritten. Other reference styles remain unchanged.
- `--max-contexts N` and `--max-context-chars N`: bound the contexts sent to the evaluator (not the RAG pipeline). The judge reads first N results in their existing retrieval order, without re-ranking. Lower limits can affect faithfulness and must be reported.
- Automatically checkpoint and stop upon HTTP 429. Use `--resume` after quota recovery.
- `judge_settings.json` and a configuration section in `RAGAS_REPORT.md` ensure judge/model settings are documented; trying to resume scores with conflicting configurations is blocked. Use a new output directory for a new judge setup.
- Diagnostic script now shares the exact same reference normalization helper with the evaluation runner.
- Additional offline tests requiring no Groq calls.

## Install (PowerShell)

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\ReportLens_AI_RAGAS_Qwen_Low_Quota_Fix.zip" -DestinationPath "C:\Projects" -Force
cd C:\Projects\reportlens-ai
python -m pytest -q
```

## First: factual correctness only, two-question Qwen pilot

This metric does **not** need large retrieved-context strings, so run it separately first:

```powershell
python -m evaluation.ragas_eval --input evaluation\results_after_fix_rescored\results.json --output-dir evaluation\results_after_fix_rescored\ragas_qwen_factual_contextualized --model qwen/qwen3.8-27b --metrics factual_correctness --reference-mode contextualized --limit 2 --delay 20
```

If it hits a 429, respect the recovery interval and repeat **the exact same command adding `--resume`**.

## Next: faithfulness only with bounded retrieved context

```powershell
python -m evaluation.ragas_eval --input evaluation\results_after_fix_rescored\results.json --output-dir evaluation\results_after_fix_rescored\ragas_qwen_faithfulness_limited --model qwen/qwen3.8-27b --metrics faithfulness --max-contexts 2 --max-context-chars 1800 --limit 2 --delay 65
```

This changes the judge evidence window and **can change measured faithfulness**. The cap only affects the evaluation input; the saved 35-question retrieval contexts stay intact. Do not compare the resulting scores as if they were scored with the original nine full passages.

For Q01 in the uploaded checkpoint, the faithfulness context reduces from 14,820 characters to 3,600 while retaining the consolidated financial statement evidence at the start of the first result. Actual token usage includes metric instructions and the model's output, so a 429 remains possible.

## After pilots succeed

Run the factual correctness evaluator on all 30 answerable questions with the same output directory, **removing `--limit 2` but keeping `--resume`**. Stop/restart safely upon quota 429. Keep judge model and reference mode constant; do not mix judge providers in a single score report.

Inspect `ragas_scores.json`, `RAGAS_REPORT.md`, and `judge_settings.json`. A score of 0 or 1 from the judge is not equivalent to independently validated financial correctness or citation support.

## Validation

The patch passed 63 local pytest tests in the available project snapshot, including 7 new tests. The user's Windows project had 71 passing tests before this patch; the number may differ from this snapshot. No live Groq judge calls were performed while testing the patch.
