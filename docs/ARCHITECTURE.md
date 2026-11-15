# Architecture and design choices

## Retrieval

The current fast build uses SQLite FTS5 lexical retrieval for both the permanent report index and temporary per-user uploads. No embedding model download is required at cloud startup; the original plan's ChromaDB / MiniLM was intentionally replaced for lower memory and faster initialization. Do not claim vector-semantic retrieval.

## Separation

- Permanent source: checked-in read-only SQLite database (`data/index/reference_reports.sqlite3`).
- Per-session source: separate in-memory SQLite database in Streamlit session state.
- Retrieval: lexical matching plus special-case verified financial-statement extraction and company routing.
- Generation: Groq only when deterministic extraction cannot directly answer a question.
- Citation behavior: evidence identified by source ID, filename and PDF page; citation-ID validity does not establish all claims are supported.

## Resource and privacy constraints

The original PDFs are not needed for startup. User uploads do not persist across Streamlit sessions or restarts. Source excerpts supplied to Groq leave the Streamlit app and are processed by the external provider. Avoid confidential material unless provider processing is acceptable. App testing has not established multi-user concurrency capacity or production throughput.
