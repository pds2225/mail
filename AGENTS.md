# AGENTS.md

## Cursor Cloud specific instructions

### Overview
This is a Korean Government Grant & Export Support Announcement Monitoring System. It scrapes ~70+ Korean government/agency websites, deduplicates, filters by date/group criteria, summarizes with Claude AI, and emails digests.

### Services

| Service | Command | Port | Notes |
|---------|---------|------|-------|
| Streamlit Dashboard | `python3 -m streamlit run streamlit_app.py --server.headless true --server.port 8501` | 8501 | Admin UI for managing sources, groups, settings |
| Monitor (one-shot) | `python3 monitor.py` | N/A | Requires real API keys — will crash without `BIZINFO_API_KEY`, `ANTHROPIC_API_KEY`, `GMAIL_APP_PASSWORD` |

### Running Tests

- **Unit tests (no API keys needed):** `python3 test_monitor.py` — tests dedup, date filter, group filter, support type classification using mock data.
- **Integration fetch tests (needs BIZINFO_API_KEY):** `python3 test_fetch.py` — makes real HTTP requests to configured sites.

### Linting

No linting tool is configured in the repo. Use `python3 -m ruff check .` if `ruff` is installed. Existing code has style warnings (semicolons, multi-imports) that are intentional code style choices by the author.

### Key Gotchas

- `monitor.py` reads env vars at module import time (`os.environ["BIZINFO_API_KEY"]` etc.), so importing it without those vars set will crash. The test files use `os.environ.setdefault(...)` to work around this.
- The Streamlit app (`streamlit_app.py`) does NOT require any API keys — it only manages JSON config files and can launch `monitor.py` as a subprocess.
- Use `python3` not `python` — no `python` symlink exists in this environment.
- JSON config files (`sites.json`, `groups.json`, `settings.json`) are the data store — no database needed.
- `seen_ids.json` is auto-generated at runtime and git-ignored.
