# ReportLens AI — Phase 8: Testing and Optimization

This incremental patch targets the current **SQLite FTS5 / session-only PDF+CSV** application. It does not replace the permanent TCS index, Groq credentials, Phase 7 checkpoint, or original ground-truth files. It does **not** add embeddings or ChromaDB, which were replaced earlier for faster local performance.

## Files included

| File | Purpose |
|---|---|
| `app.py` | Use reusable upload validation and session cleanup; safer public error messages |
| `src/fast_rag.py` | Reject malformed CSVs and verify LLM citation IDs before displaying answers |
| `src/upload_policy.py` | Session upload caps, duplicate checks, filename sanitization |
| `src/session_utils.py` | Chat-only reset versus clear-all-upload reset |
| `src/response_safety.py` | Citation ID validation and safe, nonsecret exception messages |
| `tests/test_phase8_integrations.py` | Offline regression tests: PDFs, CSVs, limits, indexing, routing, isolation, citations |
| `scripts/phase8_verify.py` | Reproducible smoke + timing report without Groq |
| `phase8/results/*` | Baseline measurements recorded in the build workspace (Linux) |

## Install on Windows PowerShell

Stop Streamlit with `Ctrl+C` before replacing files.

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\ReportLens_AI_Phase8_Testing_Optimization.zip" -DestinationPath "C:\Projects" -Force
cd C:\Projects\reportlens-ai
.\.venv\Scripts\Activate.ps1
python -m pytest -q
python -m scripts.phase8_verify
streamlit run app.py
```

Your Windows report will be saved in `phase8/results/metrics.json` and `phase8/results/PHASE8_REPORT.md`.

## Manual browser checklist (still required)

1. Verify the four TCS reports appear in the permanent list. Ask about TCS annual revenues and inspect both figures and linked PDF pages.
2. Upload an Infosys PDF and a small CSV; verify that **TCS-only** queries never retrieve Infosys and that explicit comparison queries include evidence from each company.
3. Ask a CSV total/average question. Verify the arithmetic against the raw CSV.
4. Click **New chat**: conversation history should disappear but uploaded documents should remain. Click **Clear private uploads**: private files and conversation should disappear while the four permanent reports remain.
5. Use two private/incognito browser sessions; upload distinct PDFs/CSVs and verify each session sees only its own temporary uploads.
6. Attempt duplicate upload, sixth upload, oversized PDF/CSV, a 501-page PDF, corrupted PDF, encrypted PDF, and scanned PDF. Verify the correct error text, no app crash, and no partial index poisoning.
7. Ask a general descriptive question that reaches Groq. Confirm every factual response has source citations; hallucinated source IDs must be rejected rather than displayed.
8. Confirm Groq 429 and timeout messages are user-friendly and do not reveal secrets or internal exception text.

## Coverage and limitations

- Offline tests do not replace a real Streamlit browser smoke test or cross-user concurrent load test.
- Error handling and citation-ID checks are structural safeguards, **not semantic correctness proof**. A valid `[S1]` token is not proof that source S1 supports every claim.
- The final full-set RAGAS factual scores were incomplete and 18 faithfulness cases had valid scores; we do not infer missing scores.
- The synthetic PDF test exercises empty-page detection via a controlled PyMuPDF stub because PyMuPDF cannot serialize zero-page PDFs.
- The diagnostic script reports Python allocation peaks via `tracemalloc`, not the true full-process RSS (PyMuPDF and SQLite may allocate outside Python).
- The current app is lexical RAG with some deterministic financial extraction; it does not meet the original ChromaDB/embedding requirement verbatim.
- Scanned/image-only PDFs currently need OCR and are intentionally rejected with an explanatory message.
- Uploaded files and chats live in private in-memory session state, not durable cross-restart storage.
- Live Groq latency/429 recovery was previously explored in Phase 7 but is not re-benchmarked here to avoid consuming quota.

## Phase 8 gate

Phase 8 **offline/backend verification** can be marked complete after Windows tests and `scripts.phase8_verify` pass. The **browser/end-to-end** gate remains open until the above manual steps are executed. Phase 9 will cover Streamlit Community Cloud deployment, secrets, dependency freeze, repository documentation, and public URL verification.
