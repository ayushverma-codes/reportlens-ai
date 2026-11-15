# Phase 9 — GitHub + Streamlit Community Cloud deployment

This release is **prepared for deployment, not yet publicly deployed**. Streamlit Community Cloud reads GitHub source, installs dependencies from `requirements.txt` and launches `app.py`. The original large TCS PDFs are not needed because the repository includes the read-only 8.9 MiB FTS index.

## 1. Preflight on your Windows machine

```powershell
cd C:\Projects\reportlens-ai
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m scripts.phase9_preflight
python -m scripts.phase8_verify
```

Check that the preflight report says the TCS index is readable. API key is not required for index verification; it is required for Groq-generated answers.

## 2. Check repository safety BEFORE committing

`.gitignore` excludes `.env`, `.streamlit/secrets.toml`, source PDFs, uploaded documents, virtual environments and `evaluation/results*/` files. Run:

```powershell
git status --short
git check-ignore .env .streamlit/secrets.toml evaluation/results_after_fix_rescored/results.json
```

If any sensitive files were committed earlier, `.gitignore` does NOT remove them from Git history. Stop and remove them from tracking (and rotate exposed keys) before publishing; do not assume a private repository makes an exposed key safe.

## 3. Initialize or update GitHub repository

Create a GitHub repository named `reportlens-ai` with your own GitHub account. Do not auto-generate a README if initializing an empty repo. If your local repo already exists, keep its current Git history and remote rather than running `git init` again.

```powershell
# Run only if the project is not already a Git repository:
git init

git branch -M main

# Stage ONLY the deployment-safe source, index and public docs.
git add .gitignore .gitattributes .env.example .streamlit/config.toml .streamlit/secrets.toml.example .github/workflows/tests.yml README.md PROJECT_STATUS.md DECISIONS.md app.py src/ scripts/ tests/ evaluation/*.py evaluation/ground_truth/ requirements.txt requirements-dev.txt requirements-eval.txt data/index/reference_reports.sqlite3 docs/

git diff --cached --name-only
python -m scripts.phase9_preflight --check-git

git commit -m "Prepare ReportLens AI for Streamlit Cloud deployment"
```

Inspect `git diff --cached --name-only` manually. It must not contain `.env`, a populated `secrets.toml`, user uploads, source PDFs or saved answer outputs.

For a new repository, add your actual URL (substitute your GitHub username):

```powershell
git remote add origin https://github.com/YOUR_USERNAME/reportlens-ai.git
git push -u origin main
```

For an existing remote, check `git remote -v` and use `git push origin main`; do not add a duplicate `origin`. If the repository already tracks secrets or historical large files, clean it before pushing.

### Index-size note

`data/index/reference_reports.sqlite3` should appear in the commit. If missing, Cloud will start without the bundled TCS reports. The source PDFs are intentionally absent. Verify licensing and whether the extracted-text index may be redistributed before making a public repository; use private visibility if appropriate.

## 4. Deploy on Streamlit Community Cloud

1. Sign in at https://share.streamlit.io with GitHub.
2. Choose **Create app / Deploy an app**, then select the `reportlens-ai` repository and `main` branch.
3. Set entrypoint to `app.py` (repo root).
4. In **Advanced settings**, choose **Python 3.13** (tested in the offline Linux environment).
5. In Cloud **Secrets**, supply the following, using your real key privately:

```toml
GROQ_API_KEY = "YOUR_ACTUAL_GROQ_KEY"
GROQ_MODEL = "openai/gpt-oss-20b"
```

6. Save settings and deploy. **Never paste your key into Git or screenshots.**
7. Inspect build logs and the app itself. The URL is not verified until you can open and test it.

Note: Streamlit Cloud defaults may vary; Python version is selected at initial deployment, and changing it later may require redeployment.

## 5. Production smoke-test checklist

- [ ] Public application loads without a missing-module or SQLite error.
- [ ] Sidebar displays **Permanent reports (4/4)**.
- [ ] Ask **TCS annual revenues**; verify FY labels and cited PDF pages.
- [ ] Ask a broad grounded question; check Groq API response and citations.
- [ ] Upload a small PDF and CSV; retrieve and calculate from each.
- [ ] Delete an upload; confirm it is no longer searchable.
- [ ] Use New Chat; confirm uploaded documents remain but conversation clears.
- [ ] Open a second browser/private window; verify it cannot access the first session's uploads.
- [ ] Restart the hosted app if possible; confirm permanent index remains while private uploads are not guaranteed to persist.
- [ ] Monitor Streamlit Cloud logs for resource and quota failures.

If `Permanent reports (0/4)` appears, ensure the sqlite3 index is committed at the correct path. If answers fail with Groq `429`, inspect per-model rate limits; this is not a missing-index error. If `no such module: fts5`, check runtime SQLite compile options (Python distributions normally include FTS5).

## 6. Shareable deliverables

After the live smoke test succeeds, record the verified GitHub repository link, Streamlit app URL, deployed commit hash and one screenshot in your project notes. Do not claim public deployment success until the live URL has been tested.

Official references:
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies
