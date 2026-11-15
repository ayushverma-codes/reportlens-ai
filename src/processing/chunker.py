"""Page-bounded structure-aware narrative and table-aware chunking."""
import re
import hashlib
from dataclasses import dataclass, asdict
from config.settings import settings

@dataclass
class Chunk:
    id: str
    text: str
    document_id: str
    filename: str
    pdf_page_number: int
    printed_page_number: str | None
    content_type: str
    section: str = ''

def _parts(text: str):
    """Split at paragraphs; split oversized paragraphs at sentence boundaries."""
    for paragraph in re.split(r'\n\s*\n', text):
        paragraph = re.sub(r'[ \t]+', ' ', paragraph.strip())
        if not paragraph:
            continue
        if len(paragraph.split()) <= 400:
            yield paragraph
        else:
            for sentence in re.split(r'(?<=[.!?])\s+', paragraph):
                for i in range(0, len(sentence.split()), 350):
                    yield ' '.join(sentence.split()[i:i+350])

def chunk_document(document, *, target_tokens: int = settings.chunk_tokens,
                   overlap_tokens: int = settings.overlap_tokens) -> list[Chunk]:
    if target_tokens <= overlap_tokens or overlap_tokens < 0:
        raise ValueError('Target must exceed overlap')
    results = []
    for page in document.pages:
        heading = ''
        if page.text:
            lines = [line.strip() for line in page.text.splitlines() if line.strip()]
            heading = next((line for line in lines[:8] if 4 < len(line) < 100 and not re.search(r'\.{5,}', line)), '')
        parts = list(_parts(page.text))
        current = []
        def emit(items, kind='narrative'):
            if not items:
                return
            body = '\n\n'.join(items)
            content = f'Section: {heading}\n{body}' if heading else body
            ident = hashlib.sha256(f'{document.document_id}:{page.pdf_page_number}:{kind}:{len(results)}'.encode()).hexdigest()
            results.append(Chunk(ident, content, document.document_id, document.filename,
                                 page.pdf_page_number, page.printed_page_number, kind, heading))
        for part in parts:
            if current and len((' '.join(current)+' '+part).split()) > target_tokens:
                emit(current)
                preceding = ' '.join(current).split()[-overlap_tokens:] if overlap_tokens else []
                current = [' '.join(preceding)] if preceding else []
            current.append(part)
        emit(current)
        for table in page.tables:
            if not table:
                continue
            header = ' | '.join(table[0])
            # Preserve column alignment, repeat the heading and headers for every group.
            group = []
            for row in table[1:]:
                line = ' | '.join(row)
                if group and len((' '.join(group) + line).split()) > target_tokens:
                    emit([f'Table on page {page.pdf_page_number}', header, *group], 'table')
                    group = []
                group.append(line)
            emit([f'Table on page {page.pdf_page_number}', header, *group], 'table')
    return results
