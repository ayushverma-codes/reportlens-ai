def build_context(hits):
    return '\n\n'.join(
        f'[S{i}] Document: {hit["metadata"]["filename"]}; PDF page: {hit["metadata"]["pdf_page_number"]}\n'
        f'{hit["text"][:4000]}'
        for i,hit in enumerate(hits,1)
    )
