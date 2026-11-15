# Phase 7 — Evaluation summary

Evaluation dataset: **35 TCS questions** (8 factual, 5 numerical, 7 comparison, 8 analysis, 2 summary, 5 unanswerable). Evaluation used the previously generated answers (Groq GPT-OSS-20B), reference-number checks, and RAGAS with Groq-hosted Qwen3.8-27B as a judge.

| Measurement | Observed result | Denominator and caution |
|---|---:|---|
| Full answer generation | 35/35 | No API errors in the completed baseline run |
| Expected-document retrieval | 30/30 | Top-9 filename coverage only, not page accuracy |
| Reference-number coverage after fixes | 100% | For applicable numeric cases; not complete answer correctness |
| Unanswerable abstention accuracy after rescoring | 5/5 | Includes a corrected false negative for valid refusal language |
| RAGAS factual correctness | 0.433 | 27 cases scored of 30, 3 unscored due to structured output length |
| RAGAS faithfulness | 0.880 | 18 cases scored of 30, restricted evidence window (2 passages of 1,800 chars) |

The observed mean excludes unscored entries. **There is no measured full-30 RAGAS average.** We do not impute values for missing scores. The two RAGAS metrics answer different questions and cannot be reduced to a single accuracy percentage. Some Qwen judge factual scores disagree with deterministic numerical checks; a claim-level reference audit is still recommended. Citation ID parsing improvements do not by themselves establish source support.

Evaluation code is under `evaluation/`; original benchmark files are under `evaluation/ground_truth/`. Private per-run outputs under `evaluation/results*/` are ignored by Git. To reproduce RAGAS locally, install `requirements-eval.txt` and configure Groq credentials; quota and model capacity may affect reproducibility.
