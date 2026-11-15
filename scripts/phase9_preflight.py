"""Offline Phase 9 release check; makes no network calls and prints no secrets.

Usage: python -m scripts.phase9_preflight [--check-git] [--require-key]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'data' / 'index' / 'reference_reports.sqlite3'
EXPECTED = ('documents', 'chunks', 'chunks_fts')


def inspect_index(path: Path = INDEX) -> dict:
    """Check indexed data without requiring original PDFs or writing to SQLite."""
    if not path.is_file():
        return {'passed': False, 'details': f'Missing index: {path}'}
    try:
        with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as con:
            names = {x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
            if not set(EXPECTED).issubset(names):
                return {'passed': False, 'details': f'Index schema incomplete: {sorted(names)}'}
            docs, pages, chunks = con.execute(
                'SELECT COUNT(*), COALESCE(SUM(page_count),0), COALESCE(SUM(chunk_count),0) FROM documents'
            ).fetchone()
            indexed_chunks = con.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
            fts_match = con.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'revenue' LIMIT 1").fetchone()
            valid = docs == 4 and chunks == indexed_chunks and pages > 1000 and bool(fts_match)
            return {
                'passed': bool(valid),
                'details': f'{docs} reports, {pages} pages, {chunks} chunks, {path.stat().st_size} bytes; FTS5 query={bool(fts_match)}'
            }
    except (sqlite3.Error, OSError) as exc:
        return {'passed': False, 'details': f'Index not readable: {type(exc).__name__}: {exc}'}


def sensitive_tracked_paths(root: Path = ROOT) -> tuple[list[str], str | None]:
    """Find already-tracked secret/private paths; gitignore cannot fix those retroactively."""
    if not shutil.which('git'):
        return [], 'Git executable is not available'
    probe = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=root,
                           text=True, capture_output=True, check=False)
    if probe.returncode:
        return [], 'Directory is not yet a Git repository'
    tracked = subprocess.run(['git', 'ls-files', '-z'], cwd=root,
                             capture_output=True, check=False)
    if tracked.returncode:
        return [], 'Cannot enumerate Git tracked files'
    files = [s.replace('\\', '/') for s in tracked.stdout.decode('utf-8', errors='replace').split('\0') if s]
    suspects = []
    for name in files:
        lower = name.lower()
        if (lower == '.env' or lower.startswith('.env.') and lower != '.env.example'
                or lower == '.streamlit/secrets.toml' or lower.startswith('.streamlit/secrets.') and lower != '.streamlit/secrets.toml.example'
                or lower.startswith(('data/reports/', 'data/uploads/', 'uploads/',
                                     'evaluation/results/', 'evaluation/results_', 'phase9/results/'))
                or lower.endswith(('.pem', '.key', '.pdf'))):
            suspects.append(name)
    return sorted(suspects), None


def collect(root: Path = ROOT, *, check_git: bool = False, require_key: bool = False) -> dict:
    checks = []
    def add(name: str, passed: bool, details: str):
        checks.append({'name': name, 'passed': bool(passed), 'details': details})

    files = [
        'app.py', 'requirements.txt', '.gitignore', '.env.example',
        '.streamlit/config.toml', '.streamlit/secrets.toml.example',
        'docs/DEPLOYMENT.md', 'docs/EVALUATION.md', 'docs/TESTING.md',
    ]
    missing = [name for name in files if not (root / name).is_file()]
    add('deployment_files', not missing,
        'All required deployment files present' if not missing else f'Missing: {", ".join(missing)}')

    data = inspect_index(root / 'data/index/reference_reports.sqlite3')
    add('reference_index', data['passed'], data['details'])
    ignored = (root / '.gitignore').read_text(encoding='utf-8') if (root / '.gitignore').is_file() else ''
    for fragment in ('.env', '.streamlit/secrets.toml', 'data/reports/', 'evaluation/results'):
        add('ignore_' + fragment.replace('/', '_').replace('.', '_'),
            fragment in ignored, f'{fragment} rule present' if fragment in ignored else f'No {fragment} rule')

    if require_key:
        key = bool(os.environ.get('GROQ_API_KEY', '').strip())
        # Local .env is intentionally not read or displayed; users can set env explicitly.
        add('groq_api_key', key, 'Present in process environment' if key else 'Missing from process environment')

    if check_git:
        files, reason = sensitive_tracked_paths(root)
        add('git_tracked_file_safety', reason is None and not files,
            reason or ('Unexpected tracked paths: ' + ', '.join(files) if files else 'No tracked secrets, PDFs, or private results'))
        if reason is None:
            cmd = subprocess.run(['git', 'ls-files', '--error-unmatch', 'data/index/reference_reports.sqlite3'],
                                 cwd=root, capture_output=True, text=True, check=False)
            add('index_is_git_tracked', cmd.returncode == 0,
                'Permanent index staged/tracked' if cmd.returncode == 0 else 'Index is not staged/tracked')

    return {
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'passed' if all(c['passed'] for c in checks) else 'failed',
        'checks_passed': sum(c['passed'] for c in checks),
        'checks_total': len(checks),
        'checks': checks,
        'notes': 'Offline release inspection only; no hosted app or public deployment has been verified.'
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-git', action='store_true', help='Verify no private files tracked and reference index staged/tracked')
    parser.add_argument('--require-key', action='store_true', help='Require GROQ_API_KEY in process environment')
    parser.add_argument('--output-dir', default='phase9/results')
    args = parser.parse_args()
    result = collect(check_git=args.check_git, require_key=args.require_key)
    dest = ROOT / args.output_dir
    dest.mkdir(parents=True, exist_ok=True)
    (dest / 'preflight.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    lines = ['# Phase 9 — Deployment Preflight', '',
             f"**{result['status'].upper()} — {result['checks_passed']}/{result['checks_total']} checks**", '',
             '| Check | Result | Details |', '|---|---|---|']
    for c in result['checks']:
        lines.append(f"| {c['name']} | {'PASS' if c['passed'] else 'FAIL'} | {c['details'].replace('|', ' / ')} |")
    lines += ['', 'This is a local release check, **not proof of successful cloud deployment**.']
    (dest / 'PREFLIGHT_REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    for c in result['checks']:
        print(f"{'PASS' if c['passed'] else 'FAIL'} {c['name']}: {c['details']}")
    print(f"Phase 9 preflight: {result['status']} ({result['checks_passed']}/{result['checks_total']})")
    print(f'Report: {dest / "PREFLIGHT_REPORT.md"}')
    if result['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
