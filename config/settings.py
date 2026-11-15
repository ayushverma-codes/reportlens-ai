from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    max_files: int = 5
    max_file_bytes: int = 20 * 1024 * 1024
    max_total_bytes: int = 50 * 1024 * 1024
    max_pages: int = 500
    chunk_tokens: int = 600
    overlap_tokens: int = 100
    top_k: int = 8
    embedding_model: str = 'sentence-transformers/all-MiniLM-L6-v2'
    groq_model: str = 'openai/gpt-oss-20b'

settings = Settings()
