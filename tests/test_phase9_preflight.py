"""Offline safety and release-readiness tests."""
import sqlite3
from pathlib import Path

from scripts.phase9_preflight import collect, inspect_index


def test_bundled_reference_index_is_read_only_searchable():
    state = inspect_index()
    assert state['passed'], state['details']
    assert '4 reports' in state['details']


def test_preflight_deployment_files_and_gitignore():
    result = collect()
    assert result['status'] == 'passed', result['checks']
    assert result['checks_passed'] == result['checks_total']


def test_missing_index_fails(tmp_path):
    res = inspect_index(tmp_path / 'no_index.sqlite3')
    assert not res['passed']
    assert 'Missing index' in res['details']


def test_empty_index_fails_without_crashing(tmp_path):
    dest = tmp_path / 'empty.sqlite3'
    with sqlite3.connect(dest) as db:
        db.execute('CREATE TABLE unrelated (id INTEGER)')
    res = inspect_index(dest)
    assert not res['passed']
    assert 'schema incomplete' in res['details']


def test_real_secrets_templates_are_placeholders():
    root = Path(__file__).resolve().parents[1]
    sample = (root / '.streamlit/secrets.toml.example').read_text(encoding='utf8')
    assert 'GROQ_API_KEY' in sample
    assert 'replace_with_your_own_key' in sample
