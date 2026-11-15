# Phase 7 audit corrections — ReportLens AI

This is a **narrow patch** for the existing fast/SQLite project. It is **not** a new project.

## Includes

- `src/fast_rag.py`: normalize Groq bracket citations, avoid FY/calendar confusion, prioritize documented client-priority passages, and pass validated financial requests to a source-based extractor.
- `src/verified_financial.py`: source-based two-year financial comparisons, constant-currency decline, and industry-segment revenue/growth ranking. It has no benchmark numerical constants or hardcoded TCS answer values. It declines cross-company shortcuts.
- `src/report_intents.py`: prevent factual questions containing "report" from being treated as document-listing requests.
- `evaluation/metrics.py`: recognize `[S1]`, `[ S1 ]`, and `【S1】` in citation diagnostics.
- `evaluation/evaluate.py`: support `--rerun-ids` for selective reruns while preserving untouched results.
- `evaluation/audit_saved_results.py`: read-only postmortem audit from a saved `results.json`.
- `tests/test_phase7_regression_fixes.py`: offline regression tests for identified issues.

## Installation on Windows PowerShell

Stop Streamlit using Ctrl+C before replacing project files.

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\ReportLens_AI_Phase7_Audit_Fix.zip" -DestinationPath "C:\Projects" -Force
cd C:\Projects\reportlens-ai
.\.venv\Scripts\Activate.ps1
python -m pytest -q
python -m evaluation.audit_saved_results
```

The patch does not include or overwrite `.env`, `app.py`, the permanent SQLite index, or original `evaluation/results/results.json`.

## Targeted live rerun without losing the baseline

Create a separate results directory and copy the **original full checkpoint** into it:

```powershell
New-Item -ItemType Directory -Force evaluation\results_after_fix | Out-Null
Copy-Item evaluation\results\results.json evaluation\results_after_fix\results.json -Force
python -m evaluation.evaluate --mode full --resume --rerun-ids Q12,Q15,Q18,Q19,Q21,Q22,Q28,Q30,Q32 --sleep 65 --output-dir evaluation\results_after_fix
```

Only the selected questions are regenerated. The other records are copied from the baseline; **do not** interpret any unchanged scores as evidence that those older answers were fixed. If Groq rate-limits again, rerun the same command; the new results checkpoint survives.

For a post-rerun audit:

```powershell
python -m evaluation.audit_saved_results --input evaluation\results_after_fix\results.json --output-dir evaluation\results_after_fix\audit
```

## Verification & limitations

- 48/48 tests pass on the available project snapshot with the four-report SQLite index.
- The new *deterministic* results for Q12, Q15, Q18, Q19 and Q32 were checked against indexed report text; no Groq call was used for these tests.
- Q22 retrieval now promotes the relevant FY2026 management-discussion page. Groq answer accuracy must still be checked live.
- Q28 file-inventory false-positive is fixed; it will use grounded retrieval and Groq, rather than a file list.
- Q21 and Q30 require human review because narrative correctness/column-extraction artifacts cannot be certified by simple numeric or citation-ID checks.
- `citation_ids_valid` checks the **format and source-ID list**, not whether a source supports every claim. Earlier saved results are unchanged.
- This patch is intentionally not a full RAGAS evaluation.
