"""ReportLens AI — 4 permanent reports + private session PDF/CSV chat."""
from __future__ import annotations

import logging
import os
from contextlib import closing
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')

from src.document_routing import AUTO, COMPARE, catalog, select_docs
from src.clarification import complete_company_question
from src.upload_policy import plan_session_uploads
from src.session_utils import clear_conversation, clear_private_uploads
from src.response_safety import safe_answer_error

from src.fast_rag import (
    DB_PATH, MAX_UPLOADS, PDF_LIMIT, CSV_LIMIT, TOTAL_UPLOAD_LIMIT,
    connect_database, list_documents, pdf_chunks, csv_chunks,
    store_document, delete_document, generate_answer,
)

st.set_page_config(page_title='ReportLens AI', page_icon='📊', layout='wide')
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
log = logging.getLogger('reportlens')


def get_api_key():
    try:
        return st.secrets.get('GROQ_API_KEY') or os.getenv('GROQ_API_KEY', '')
    except Exception:
        return os.getenv('GROQ_API_KEY', '')


def get_model_name():
    """Allow Cloud secrets to configure Groq while retaining local .env support."""
    default = os.getenv('GROQ_MODEL', 'openai/gpt-oss-20b')
    try:
        return st.secrets.get('GROQ_MODEL') or default
    except Exception:
        return default


if 'private_index' not in st.session_state:
    st.session_state.private_index = connect_database()
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'pending_question' not in st.session_state:
    st.session_state.pending_question = None
if 'notice' not in st.session_state:
    st.session_state.notice = None
if 'upload_errors' not in st.session_state:
    st.session_state.upload_errors = []
if 'awaiting_company_question' not in st.session_state:
    st.session_state.awaiting_company_question = None

reference_exists = DB_PATH.is_file()
reference_docs = []
if reference_exists:
    try:
        with closing(connect_database(DB_PATH, readonly=True)) as ref:
            reference_docs = list_documents(ref)
    except Exception as e:
        st.error(f'Permanent index could not be opened: {e}')
        reference_exists = False

uploaded_docs = list_documents(st.session_state.private_index)

with st.sidebar:
    st.header('Documents')
    st.subheader(f'Permanent reports ({len(reference_docs)}/4)')
    if reference_docs:
        with st.expander('See permanent annual reports', expanded=False):
            for item in reference_docs:
                st.caption(f"📘 {item['filename']} — {item['page_count']} pages")
    else:
        st.warning('Permanent reports are not indexed yet.')
        st.code('python -m scripts.build_permanent', language='powershell')

    st.divider()
    st.subheader(f'Private uploads ({len(uploaded_docs)}/{MAX_UPLOADS})')
    uploads = st.file_uploader(
        'Upload PDF or CSV files', type=['pdf', 'csv'],
        accept_multiple_files=True,
        help='Up to 5 session files; PDFs ≤20 MiB and ≤500 pages; CSVs ≤10 MiB; 50 MiB total.',
    )
    if st.button('Index selected uploads', disabled=not uploads, use_container_width=True):
        plan = plan_session_uploads(uploads, uploaded_docs)
        st.session_state.upload_errors = list(plan.errors)
        if plan.duplicates:
            st.info(f'{plan.duplicates} duplicate upload(s) skipped.')
        if not plan.candidates and not plan.errors and not plan.duplicates:
            st.info('No eligible files selected.')
        for candidate in plan.candidates:
            name, data, kind = candidate.filename, candidate.data, candidate.kind
            bar = st.progress(0.0, text=f'Extracting {name}...')
            try:
                if kind == 'pdf':
                    count, chunks = pdf_chunks(
                        data, progress=lambda x: bar.progress(x, text=f'Reading {name}: {x:.0%}'))
                else:
                    count, chunks = csv_chunks(
                        data, progress=lambda x: bar.progress(x, text=f'Reading {name}: {x:.0%}'))
                bar.progress(1.0, text=f'Indexing {name}...')
                stored = store_document(
                    st.session_state.private_index, candidate.doc_id, name, kind,
                    count, len(data), chunks)
                st.session_state.notice = (
                    f'Indexed {name}: {count} pages/rows; {stored} searchable chunks.')
                log.info(st.session_state.notice)
            except Exception as exc:
                log.exception('Failed to index %s', name)
                message = f'{name}: {exc}'
                st.session_state.upload_errors.append(message)
            finally:
                bar.empty()
        if plan.candidates:
            st.rerun()

    if st.session_state.notice:
        st.success(st.session_state.notice)
        st.session_state.notice = None
    if st.session_state.upload_errors:
        for error in st.session_state.upload_errors:
            st.error(error)
        st.session_state.upload_errors = []

    uploaded_docs = list_documents(st.session_state.private_index)
    for item in uploaded_docs:
        left, right = st.columns([5, 1])
        left.caption(f"{item['filename']} — {item['page_count']} {'pages' if item['kind']=='pdf' else 'rows'}")
        if right.button('✕', key='remove_' + item['doc_id'], help='Remove this session file'):
            delete_document(st.session_state.private_index, item['doc_id'])
            clear_conversation(st.session_state)
            st.rerun()

    if uploaded_docs and st.button('Clear private uploads', use_container_width=True):
        clear_private_uploads(st.session_state)
        st.rerun()

    if st.button('New chat', use_container_width=True):
        clear_conversation(st.session_state)
        st.rerun()

    st.divider()
    scope = st.radio('Search in', ['All available documents', 'Permanent reports only', 'My uploads only'], index=0)
    groups = catalog(reference_docs, uploaded_docs,
                     include_permanent=scope != 'My uploads only',
                     include_uploads=scope != 'Permanent reports only')
    options = [AUTO] + list(groups)
    if len(groups) > 1:
        options.append(COMPARE)
    company_selection = st.selectbox('Company / file', options=options,
                                    help='In Auto mode, an unnamed company question asks for clarification rather than mixing reports.')
    st.caption('Permanent report indexes survive restarts. Uploaded files and chats are private to this session and disappear when the session ends.')

st.title('📊 ReportLens AI')
st.caption('Turn complex business reports and CSV data into traceable answers.')
st.caption('Ask for **TCS annual revenues**, **Infosys FY 2025-26 revenue**, or **compare TCS and Infosys**. When multiple companies are available, select one in the sidebar or mention its name.')

active_permanent = reference_exists and bool(reference_docs) and scope != 'My uploads only'
active_private = bool(uploaded_docs) and scope != 'Permanent reports only'
ready = active_permanent or active_private
if ready:
    st.success(f"Ready: {len(reference_docs) if active_permanent else 0} permanent report(s) + {len(uploaded_docs) if active_private else 0} private upload(s).")
else:
    st.info('Index the four permanent reports or upload a PDF/CSV to start chatting.')

if not get_api_key():
    st.warning('Add GROQ_API_KEY to your .env file or Streamlit Secrets to enable answers.')

for msg in st.session_state.messages:
    with st.chat_message(msg['role']):
        st.markdown(msg['content'])
        if msg.get('sources'):
            with st.expander('Evidence and citations'):
                for s in msg['sources']:
                    st.markdown(f"**[{s['id']}] {s['filename']} — {s['location']}**")
                    st.caption(s['excerpt'])

question = st.chat_input('Ask about your reports or CSVs...', disabled=not ready)
if question and question.strip():
    st.session_state.messages.append({'role':'user', 'content':question.strip(), 'sources':[]})
    st.session_state.pending_question = question.strip()
    st.rerun()

if st.session_state.pending_question:
    pending = st.session_state.pending_question
    st.session_state.pending_question = None
    # If the last turn asked for a company, 'Infosys' must complete the
    # ORIGINAL question instead of becoming a new topic about Infosys.
    original_intent = st.session_state.awaiting_company_question
    effective_question = complete_company_question(pending, original_intent, groups) or pending
    st.session_state.awaiting_company_question = None
    history = st.session_state.messages[:-1]
    with st.chat_message('assistant'):
        try:
            with st.spinner('Searching evidence and generating an answer...'):
                allowed_ids, clarification, company = select_docs(
                    effective_question, groups, company_selection, history
                )
                if clarification:
                    # Remember this question until the next user's company-only reply.
                    if clarification.startswith('Which company or file'):
                        st.session_state.awaiting_company_question = effective_question
                    result = {'answer': clarification, 'sources': []}
                else:
                    reference_connection = connect_database(DB_PATH, readonly=True) if active_permanent else None
                    try:
                        result = generate_answer(
                            effective_question, reference_connection,
                            st.session_state.private_index if active_private else None,
                            history, get_api_key(), get_model_name(),
                            allowed_doc_ids=allowed_ids, company_scope=company)
                    finally:
                        if reference_connection:
                            reference_connection.close()
            st.session_state.messages.append({'role':'assistant', 'content':result['answer'], 'sources':result['sources']})
            st.rerun()
        except Exception as exc:
            log.exception('Answer generation failed')
            message = safe_answer_error(exc)
            st.error(message)
            st.session_state.messages.append({'role':'assistant','content':message,'sources':[]})
