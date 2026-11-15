"""One-time indexing: python -m scripts.build_permanent"""
from pathlib import Path
import hashlib
import sqlite3
import sys

from src.fast_rag import DB_PATH, connect_database, pdf_chunks, store_document, list_documents

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'data' / 'reports'
NAMES = [
    'annual-report-2022-2023.pdf',
    'annual-report-2023-2024.pdf',
    'annual-report-2024-2025.pdf',
    'TCS_Annual_Report_2025-26.pdf',
]


def main():
    missing = [p for n in NAMES if not (p := REPORTS / n).is_file()]
    if missing:
        print('Missing original reports in data/reports/:')
        for p in missing:
            print(' -', p.name)
        return 1
    db = connect_database(DB_PATH)
    indexed = {d['doc_id'] for d in list_documents(db)}
    for name in NAMES:
        path = REPORTS / name
        data = path.read_bytes()
        doc_id = hashlib.sha256(data).hexdigest()
        if doc_id in indexed:
            print('SKIP, already indexed:', name, flush=True)
            continue
        print('Extracting:', name, flush=True)
        pages, chunks = pdf_chunks(data, upload=False)
        n = store_document(db, doc_id, name, 'pdf', pages, len(data), chunks)
        print(f'INDEXED {name}: {pages} pages, {n} chunks', flush=True)
    print('Permanent index:', DB_PATH, flush=True)
    print('Permanent document count:', len(list_documents(db)), flush=True)
    db.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
