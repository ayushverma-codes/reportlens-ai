"""Small deterministic responses to document-catalog requests.

These questions concern *what files are available*, not claims inside a PDF.
They should not be passed to lexical retrieval or an LLM.
"""
from __future__ import annotations

import re
from typing import Any


_SUBJECT = {"report", "reports", "pdf", "pdfs", "document", "documents", "file", "files", "uploads"}
_FILTER = {"annual", "financial", "uploaded", "indexed", "available", "permanent", "private", "my", "your", "all"}
_DISCOVERY = {"list", "show", "display", "available", "uploaded", "indexed", "which", "what", "many", "have", "see"}
_NOT_INVENTORY = {"summarize", "summary", "explain", "analyze", "analyse", "compare", "revenue", "revenues",
                  "profit", "expenses", "growth", "risks", "strategy", "chairman", "ceo", "total", "earnings"}


def is_document_listing_request(question: str) -> bool:
    """Identify explicit inventory questions without hijacking report analysis.

    In particular, "What controls support financial reporting according to
    the FY 2025-26 report?" is a CONTENT question, not a file-list request.
    """
    cleaned = re.sub(r"[^a-z0-9]+", " ", question.casefold()).strip()
    words = cleaned.split()
    if not words or not set(words).intersection(_SUBJECT):
        return False
    if set(words).intersection(_NOT_INVENTORY):
        return False
    if all(w in _SUBJECT | _FILTER | {"the"} for w in words):
        return True
    if len(words) > 15:
        return False
    # Only dedicated document-inventory actions (list/show/how many/which
    # reports) qualify. Generic "what ... according to report" never does.
    if re.match(r"^(?:list|show|display|see)\b", cleaned):
        return True
    if re.match(r"^(?:how many)\s+", cleaned) and len(words) <= 10:
        return True
    if re.match(r"^which\s+(?:(?:annual|financial|uploaded|available|my|your|all)\s+)*"
                r"(?:reports?|pdfs?|documents?|files?)\b", cleaned):
        return True
    if re.match(r"^what\s+(?:(?:annual|financial|uploaded|available|my|your|all)\s+)*"
                r"(?:reports?|pdfs?|documents?|files?)\b", cleaned):
        return True
    if re.match(r"^what\s+documents?\s+do\s+you\s+have\??$", cleaned):
        return True
    return False


def document_listing_answer(
    question: str,
    permanent: Any,
    temporary: Any,
    allowed_doc_ids: set[str] | None = None,
) -> dict | None:
    """Return available filenames and PDF page counts, respecting active scope."""
    if not is_document_listing_request(question):
        return None

    # Import inside function to avoid creating an import cycle with fast_rag.
    from src.fast_rag import list_documents

    sections = []
    total = 0
    for label, connection in (("Permanent reports", permanent), ("Private session uploads", temporary)):
        if connection is None:
            continue
        docs = [d for d in list_documents(connection)
                if allowed_doc_ids is None or d["doc_id"] in allowed_doc_ids]
        # 'annual reports' means PDFs, whereas 'documents' includes CSVs too.
        if re.search(r"\b(?:annual|reports?|pdfs?)\b", question.casefold()):
            docs = [d for d in docs if d["kind"] == "pdf"]
        if not docs:
            continue
        total += len(docs)
        items = []
        for doc in docs:
            kind = doc["kind"]
            qty = f"{doc['page_count']} pages" if kind == "pdf" else f"{doc['page_count']} rows"
            # SQLite stores filenames as user-controlled text; keep as code spans
            # to avoid it being interpreted as a Markdown heading or link.
            safe_filename = str(doc["filename"]).replace("`", "'").replace("\n", " ")
            items.append(f"- `{safe_filename}` — {qty}")
        sections.append(f"**{label} ({len(docs)})**\n" + "\n".join(items))

    if not total:
        return {"answer": "No matching documents are indexed in the selected search scope.", "sources": []}
    noun = "report" if total == 1 else "reports"
    return {"answer": (
        f"I have **{total} {noun}** available in the selected search scope:\n\n"
        + "\n\n".join(sections)
        + "\n\nYou can ask about revenue, profit, risks, or compare specific financial years."
    ), "sources": []}
