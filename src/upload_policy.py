"""Testable session-upload preflight for Streamlit UploadedFile objects.

Preflight enforces limits before PDF/CSV parsing. Files and indexes are kept
in the caller's private session, not in this module or a global cache.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from src.fast_rag import (
    CSV_LIMIT, MAX_UPLOADS, PDF_LIMIT, TOTAL_UPLOAD_LIMIT, content_id,
)


@dataclass(frozen=True)
class UploadCandidate:
    filename: str
    kind: str
    data: bytes
    doc_id: str


@dataclass(frozen=True)
class UploadPlan:
    candidates: tuple[UploadCandidate, ...]
    errors: tuple[str, ...]
    duplicates: int = 0


def safe_filename(name: str) -> str:
    """Remove browser paths/control characters from untrusted upload names."""
    leaf = str(name).replace('\\', '/').rsplit('/', 1)[-1]
    leaf = ''.join(c for c in leaf if c.isprintable()).strip()[:160]
    return leaf or 'unnamed'


def plan_session_uploads(files: Iterable, indexed_documents: Iterable[dict]) -> UploadPlan:
    """Deduplicate, validate and reserve session limits before indexing.

    Per-file invalid inputs are rejected while other valid files can proceed.
    Batch-level count/combined-byte violations reject the entire new batch.
    No document mutation happens here; the caller owns the transaction.
    """
    existing = list(indexed_documents)
    known = {d['doc_id'] for d in existing}
    candidates: list[UploadCandidate] = []
    errors: list[str] = []
    duplicates = 0

    for file in files:
        filename = safe_filename(getattr(file, 'name', 'unnamed'))
        suffix = Path(filename).suffix.lower()
        if suffix not in ('.pdf', '.csv'):
            errors.append(f'{filename}: only PDF or CSV files are supported.')
            continue
        file_limit = PDF_LIMIT if suffix == '.pdf' else CSV_LIMIT
        size_hint = getattr(file, 'size', None)
        if isinstance(size_hint, int) and size_hint > file_limit:
            errors.append(f'{filename}: exceeds the {file_limit // (1024*1024)} MiB file limit.')
            continue
        try:
            data = file.getvalue()
        except Exception:
            errors.append(f'{filename}: could not read uploaded bytes.')
            continue
        if not isinstance(data, bytes):
            errors.append(f'{filename}: upload contents are not bytes.')
            continue
        if len(data) > file_limit:
            errors.append(f'{filename}: exceeds the {file_limit // (1024*1024)} MiB file limit.')
            continue
        identifier = content_id(data)
        if identifier in known:
            duplicates += 1
            continue
        known.add(identifier)
        candidates.append(UploadCandidate(filename, suffix[1:], data, identifier))

    if len(existing) + len(candidates) > MAX_UPLOADS:
        errors.append(f'A maximum of {MAX_UPLOADS} session files is allowed.')
        return UploadPlan((), tuple(errors), duplicates)
    total_bytes = sum(int(d['byte_count']) for d in existing) + sum(len(c.data) for c in candidates)
    if total_bytes > TOTAL_UPLOAD_LIMIT:
        errors.append('Combined private upload size exceeds 50 MiB.')
        return UploadPlan((), tuple(errors), duplicates)
    return UploadPlan(tuple(candidates), tuple(errors), duplicates)
