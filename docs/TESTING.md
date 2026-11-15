# Phase 8 — Testing and optimization

**Windows / Python 3.14.7 — 14/14 offline backend verification checks passed** (uploaded `PHASE8_REPORT.md` and `metrics.json`, generated November 15, 2026). User also confirmed that documents can be uploaded and removed in the Streamlit UI.

| Local measurement | Result |
|---|---:|
| Four reference TCS reports | 1,382 pages, 3,096 FTS chunks |
| Prebuilt index size | 9,355,264 bytes (~8.92 MiB) |
| Retrieval p50 | 33.582 ms (16 local queries) |
| Retrieval p95 (nearest rank) | 38.745 ms (16 local queries) |
| Synthetic one-page PDF parsing | 9.763 ms |
| Synthetic two-row CSV parsing | 1,850.014 ms |
| Python `tracemalloc` peak | 38.719 MiB |

Checks include reference index integrity, synthetic PDF/CSV ingestion, number of private uploads, CSV aggregate retrieval, company scoping, cross-company retrieval, session index separation and PDF deletion.

**Not verified by this offline test:** cloud runtime, live browser concurrent sessions, Groq response latency, claim-level citation correctness, scanned PDF OCR. The reported memory is Python-tracked allocations, not process RSS. These timings are not service-level guarantees.

Reproduce the backend run:

```powershell
python -m pytest -q
python -m scripts.phase8_verify
```

Before advertising a production deployment, confirm these live browser paths: New Chat leaves uploads intact; CSV total/average is correct; cross-company comparison cites both companies; multiple browser sessions cannot access each other's uploads; and Cloud restarts leave the permanent TCS index intact.
