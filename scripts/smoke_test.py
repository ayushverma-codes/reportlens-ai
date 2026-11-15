"""Offline search smoke test: python -m scripts.smoke_test"""
from src.fast_rag import DB_PATH, connect_database, list_documents, generate_answer, retrieve

def main():
    db = connect_database(DB_PATH, readonly=True)
    try:
        docs = list_documents(db)
        print('Permanent reports:', len(docs))
        result = generate_answer('annual revenues', db, None, [], '', 'openai/gpt-oss-20b')
        print(result['answer'])
        print('Sources:', [(s['filename'], s['location']) for s in result['sources']])
        hits = retrieve('What were the total consolidated expenses in FY 2025-26?', db, None)
        print('FY2026 expense evidence:', [(h['filename'],h['location']) for h in hits[:2]])
    finally:
        db.close()

if __name__ == '__main__':
    main()
