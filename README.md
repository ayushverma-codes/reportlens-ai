# ReportLens AI

**Turn complex business reports into traceable answers.**

ReportLens AI is a lightweight Streamlit application for exploring business reports and CSV files. It ships with a **prebuilt, read-only SQLite FTS5 index** of four TCS annual reports and supports temporary user-uploaded PDFs and CSVs. Natural-language answers are generated using Groq where needed; financial summary paths may return deterministic sourced values without an LLM call.

> **Architecture note:** This fast deployment uses **SQLite FTS5 lexical retrieval**, not the originally planned MiniLM/ChromaDB embedding-based search. It should not be described as a semantic-vector retrieval implementation. AI-generated statements may require manual verification.

## Features

- Four pre-indexed TCS annual reports, ready without uploading the original large PDFs.
- Upload up to five private PDF/CSV files per session; select company and search scope.
- Ask about revenue, financial tables, business disclosures, risks, and company comparisons.
- Grounded PDF-page citations and optional evidence excerpts.
- Contextual follow-up questions, clarification when multiple companies are in scope, document deletion and New Chat.
- Session-only upload index; no permanent storage of user uploads by this app.
- Resumable, separate offline evaluation tooling with RAGAS and deterministic numerical checks.

## Architecture

```text
Streamlit UI (app.py)
  |-- reference SQLite FTS5 (data/index/reference_reports.sqlite3; read-only)
  |-- private SQLite FTS5 (per Streamlit session; in-memory)
  |-- company routing / fiscal-period handling / grounded financial summary
  |-- Groq chat completion for general document questions
  `-- source-ID and evidence rendering
```

All private document text is session-scoped in memory **inside the app**, but selected retrieved passages are sent to the external Groq API for LLM-generated answers. Do not upload confidential documents unless that external processing is acceptable. The hosting platform may impose additional logging or resource policies. PDF OCR is not available.

### Included permanent TCS reports

| Report | Financial year |
|---|---|
| `annual-report-2022-2023.pdf` | 2022–23 |
| `annual-report-2023-2024.pdf` | 2023–24 |
| `annual-report-2024-2025.pdf` | 2024–25 |
| `TCS_Annual_Report_2025-26.pdf` | 2025–26 |

The repository contains the **~8.9 MiB prebuilt index** but intentionally **excludes the source PDFs**. The index has 1,382 PDF pages and 3,096 indexed chunks. To rebuild from original reports in your own local workspace, see `scripts/build_permanent.py`.

## Local installation

Tested locally with Python 3.13 (Linux) and Python 3.14 (Windows). For Streamlit Community Cloud, choose **Python 3.13** in Advanced settings to match the offline Linux test environment. Python version is selected at initial deployment.

```powershell
cd C:\Projects\reportlens-ai
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and replace the placeholder with your real GROQ_API_KEY.
python -m scripts.phase9_preflight
streamlit run app.py
```

For unit/integration tests install `python -m pip install -r requirements-dev.txt`, then run `python -m pytest -q` and `python -m scripts.phase8_verify`. Optional RAGAS packages are listed in `requirements-eval.txt` and **should not be installed in the cloud runtime**.

## Use

1. Open the app. The sidebar should show **Permanent reports (4/4)**.
2. Ask **“TCS annual revenues”** to exercise the prebuilt index.
3. Upload one or more PDFs/CSVs through the sidebar, then choose **Index selected uploads**.
4. Choose the company or source scope for single-company questions. For cross-company requests, name both companies explicitly.
5. Inspect **Evidence and citations** for supporting PDF pages. Use **New chat** to clear conversation history while retaining uploaded documents, or delete an upload individually.

### Upload restrictions

| Policy | Limit |
|---|---|
| Session uploads | 5 files |
| Individual PDF | 20 MiB; 500 pages |
| Individual CSV | 10 MiB; 30,000 data rows |
| Total session uploads | 50 MiB |
| Accepted file types | PDF, CSV |

Unsupported: corrupted/encrypted PDFs, PDFs with no searchable text, scanned PDFs requiring OCR, unsupported CSV encodings, unextractable complex vector tables. Groq usage is subject to your account quota and model availability.

## Evaluation and performance

The TCS benchmark contains 35 questions: 8 factual, 5 numerical, 7 comparison, 8 analysis, 2 summary, 5 unanswerable. All 35 questions were processed in the full generation run. The following are **different metrics**, not interchangeable accuracy claims:

- Expected-document retrieval: **30/30** answerable questions retrieved the expected report within top nine hits. Not a page-level or claim-level precision measure.
- Reference-number coverage after targeted corrections: **100%** for applicable factual, numerical, and comparison categories. Presence of a number does not imply full answer correctness.
- Unanswerable test abstentions: **5/5**, after correcting an abstention-scoring rule.
- RAGAS Qwen factual correctness: **0.433 across 27 scored responses**, with 3 unscored (truncated judge output).
- RAGAS Qwen faithfulness: **0.880 across 18 scored responses** using at most two excerpts of 1,800 characters each; remaining cases unscored or interrupted by quota.
- Citation-ID parsing improved, but **independent citation-to-claim support audit remains outstanding**.

See [`docs/EVALUATION.md`](docs/EVALUATION.md) for methodology and limitations.

Phase 8 Windows backend: **14/14 offline checks passed**; retrieval p50 **33.582 ms** and p95 **38.745 ms** for 16 local queries, excluding LLM and UI time. See [`docs/TESTING.md`](docs/TESTING.md).

## Deployment

Follow **[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)** for a GitHub safety audit and Streamlit Community Cloud step-by-step instructions. The deployment uses `requirements.txt` and `app.py`; `GROQ_API_KEY` is supplied through Cloud **Secrets**, not Git. Verify a real public URL and online functionality before calling the app deployed.

## Project structure

```text
app.py                             Streamlit application
src/                               Retrieval, routing, ingestion safeguards, citations
scripts/                           Preflight, index build, offline verification
data/index/reference_reports.sqlite3   Bundled read-only TCS FTS index
evaluation/ground_truth/            Original 35-case benchmark
evaluation/                       Offline evaluation code (optional runtime deps)
tests/                             Automated tests
docs/                              Deployment, evaluation, testing, architecture
a .env.example                      Local API-key template
.streamlit/config.toml             Upload configuration
.streamlit/secrets.toml.example    Cloud secrets template
```

## Known limitations

- FTS5 lexical ranking can miss semantic paraphrases compared with dense retrieval.
- Some PDF tables extract imperfectly; units and dates require validation.
- Not every generated claim has independently verified page-level support.
- RAGAS results contain genuine missing scores and evaluator configuration effects.
- Session data is not persisted; hosted app restarts will clear uploads and chats.
- Hosted app performance and multi-user concurrency must be verified after deployment.

## License and data

Check licensing/redistribution permissions for the prebuilt index's source material before publishing a public repository. This repository does not include the original PDFs. Do not publish credentials, private uploads or evaluation results containing user-provided document excerpts. Choose the repository visibility accordingly.
