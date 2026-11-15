# ReportLens AI — Phase 7 evaluation

This folder is separate from the production app. **Ground-truth CSV and JSON are not modified.**

## Environment

From `C:\Projects\reportlens-ai` in an activated virtual environment:

```powershell
python -m evaluation.dataset_loader
python -m evaluation.evaluate --mode retrieval
python -m evaluation.evaluate --mode full --resume --sleep 5
```

The **offline** command measures whether expected *document filenames* appear within top-9 retrieved chunks, and saves raw retrieved contexts. It does **not** measure answer correctness, page accuracy, or RAGAS.

The **full** command uses your existing `GROQ_API_KEY` and production `GROQ_MODEL` to generate all 35 real answers. It saves results after every question in `evaluation/results/`. On a Groq rate-limit error (HTTP 429), the runner stops without losing completed results. Run the same `--resume` command again after quota resets. Do not include user-uploaded Infosys files during this benchmark; it is intentionally restricted to the four permanent TCS reports.

For a quick test, add `--limit 3` (which runs the first 3 questions). To run all 35, omit `--limit`. Running without `--resume` starts a fresh evaluation and overwrites the previous results. Keep different runs in different `--output-dir` paths if you want before/after comparisons.

Outputs: `results.json` (includes exact retrieved contexts and generated answers), `results.csv`, `summary.json`, and `EVALUATION_REPORT.md`. Values named *coverage* and *citation IDs valid* are mechanical diagnostics, **not a factual correctness verdict**. Inspect all numerical/financial items and cited PDF pages manually. Never treat a null score as zero.

## Optional RAGAS v0.4.3 judge

Run **only after full generation** has created completed answers. RAGAS may incur many evaluation requests and Groq quotas. A different judge model is preferable to the production model. Groq's OpenAI-compatible API may not satisfy every RAGAS structured-output mode; each failure is recorded rather than assigned a fabricated score.

```powershell
pip install "ragas==0.4.3" "openai>=1.82,<3" "instructor>=1.8,<2"
$env:RAGAS_EVAL_MODEL="openai/gpt-oss-20b"  # or your independently chosen judge model
python -m evaluation.ragas_eval --limit 2
python -m evaluation.ragas_eval --resume
```

Defaults: Faithfulness, Context Precision with Reference, Context Recall and Factual Correctness (RAGAS v0.4 collections API). These are not calculated for the five explicitly unanswerable questions; their abstention is evaluated separately. Answer Correctness (with semantic similarity) and Answer Relevancy additionally need a compatible embedding model. In this lightweight setup, specify `--metrics answer_relevancy` or `--metrics answer_correctness` **only with `OPENAI_API_KEY`** for the RAGAS OpenAI evaluator embeddings. That extra credential is not necessary for the other four judge metrics. Judge output: `ragas_scores.csv`, `ragas_scores.json`, `RAGAS_REPORT.md`.

The original task's technical stack requires MiniLM embeddings/ChromaDB; the current **fast** production version deliberately uses SQLite full-text search. Cite the actual architecture in your final report rather than incorrectly claiming ChromaDB or semantic retrieval was evaluated.
