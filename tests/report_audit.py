"""Development fixture audit; does not impose public upload file-size cap."""
import json
import time
from pathlib import Path
from src.ingestion.pdf_loader import load_pdf
from src.processing.chunker import chunk_document

root = Path(__file__).resolve().parents[1]
results=[]
for path in sorted((root/'data/annual_reports').glob('*.pdf')):
    start=time.monotonic()
    doc = load_pdf(path.read_bytes(),path.name,enforce_upload_limit=False,extract_page_tables=False)
    chunks=chunk_document(doc)
    summary = {**doc.summary,'narrative_chunks':len(chunks),'seconds':round(time.monotonic()-start,1),
               'sample_warnings':doc.warnings[:4], 'table_count_status':'not yet audited'}
    print(json.dumps(summary), flush=True)
    results.append(summary)
(root/'evaluation/results/extraction_summary.json').write_text(json.dumps(results,indent=2))
