# Engineering decisions and tradeoffs

1. **SQLite FTS5 vs. ChromaDB:** The optimized release uses fast, lightweight lexical retrieval to avoid model downloads and large in-memory vector indexes. This trades semantic recall for startup and resource predictability.
2. **Permanent index:** Four public TCS reports are represented by one ~8.9 MiB SQLite file. Original source PDFs are not required on the hosted app; verify redistribution rights for extracted-text index before making the repository public.
3. **User uploads:** Each Streamlit session gets an in-memory index, intentionally not durable across app restarts. The app does not save private uploads into the permanent reference index.
4. **Groq:** LLM answers use a configurable Groq model and an API key supplied through local `.env` or Streamlit Cloud Secrets. Retrieved text may be sent to the external provider for inference.
5. **Financial verification:** Deterministic methods are used when source tables can be read reliably; ambiguous values and unsupported fiscal years should not be invented.
6. **Evaluation:** Report observed denominator-bound RAGAS metrics and unscored cases. Never replace missing judge scores with inferred measurements.
7. **Deployment:** Python 3.13 is used as a tested Linux baseline for Streamlit Cloud. The cloud runtime installs only `requirements.txt`; evaluation-only packages are not deployed.
