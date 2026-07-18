# Local Study App

A local-first, open-source flashcard and quiz app with a FastAPI website and a stdio MCP server for Codex. It uses SQLite, binds only to `127.0.0.1`, and has no telemetry or runtime CDN dependencies.

## Windows quick start

```powershell
cd mcp-local-study-app
powershell -ExecutionPolicy Bypass -File scripts/install.ps1
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
Start-Process http://127.0.0.1:8080
```

Python 3.9+ is supported. Data is stored in `%LOCALAPPDATA%\local-study-app\study.db` (override with `STUDY_DATA_DIR`). The MCP server is launched with `python -m local_study_app.mcp_server` from any directory.

## Architecture

FastAPI serves a single-page vanilla JavaScript UI and JSON API. SQLite stores decks, cards, reviews, quiz sessions, and activity. The MCP server wraps the same service layer and communicates over stdio. The app never binds beyond localhost and does not contact external services.

## MCP installation

```powershell
codex mcp add local-study-app -- "C:\path\to\mcp-local-study-app\.venv\Scripts\python.exe" -m local_study_app.mcp_server
codex mcp list
```

Tools include website lifecycle (`start_study_app`, `open_study_app`, `get_study_app_status`, `stop_study_app`), deck/card CRUD, quiz generation/submission, reviews/progress, and JSON/CSV import/export.

Example prompts: “Show me my cards due today.” “Generate a quiz from Biology Basics.” “Open my local study website.” “Export my Spanish deck as CSV.”

## Tests and scripts

```powershell
powershell -ExecutionPolicy Bypass -File scripts/test.ps1
powershell -ExecutionPolicy Bypass -File scripts/stop.ps1
powershell -ExecutionPolicy Bypass -File scripts/uninstall.ps1
```

The test suite covers persistence, CRUD, imports/exports, quiz scoring, spaced repetition, health, process idempotence, and MCP tool contracts. Screenshots and the MCP test report live under `docs/`.

## Security

Inputs are typed and validated, SQL uses parameterized queries, HTML is rendered with text nodes, uploads are size-limited and parsed before commit, and import/export filenames are constrained to the application data directory. There is no generic shell MCP tool, analytics, cloud sync, or arbitrary file access.

## License

MIT.
