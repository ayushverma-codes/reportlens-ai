from config.settings import settings

def retrieve(index, query, doc_ids=None):
    return index.search(query, k=settings.top_k, document_ids=doc_ids)
