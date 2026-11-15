"""Each app session owns an independent ephemeral Chroma client."""
from src.embeddings.embedder import embed

class SessionIndex:
    def __init__(self):
        import chromadb
        self.client = chromadb.EphemeralClient()
        import uuid
        self.collection = self.client.create_collection('documents_'+uuid.uuid4().hex,
            metadata={'hnsw:space': 'cosine'})

    def add(self, chunks):
        for offset in range(0, len(chunks), 64):
            batch = chunks[offset:offset+64]
            if not batch:
                continue
            self.collection.add(ids=[c.id for c in batch], documents=[c.text for c in batch],
                embeddings=embed([c.text for c in batch]),
                metadatas=[{'document_id':c.document_id, 'filename':c.filename,
                            'pdf_page_number':c.pdf_page_number,
                            'printed_page_number': c.printed_page_number or '',
                            'content_type':c.content_type, 'section':c.section} for c in batch])

    def remove(self, document_id):
        self.collection.delete(where={'document_id': document_id})

    def search(self, query, k=8, document_ids=None):
        if not self.collection.count():
            return []
        where = {'document_id': {'$in': document_ids}} if document_ids else None
        out = self.collection.query(query_embeddings=embed([query]), n_results=min(k, self.collection.count()), where=where,
                                    include=['documents','metadatas','distances'])
        return [{'id':i, 'text':t, 'metadata':m, 'distance':d} for i,t,m,d in zip(
            out['ids'][0],out['documents'][0],out['metadatas'][0],out['distances'][0])]
