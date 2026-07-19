# MCP and application verification report

## Release candidate

- Application: Study Sprout 2.0.0
- Runtime: Python 3.9+
- Transport: newline-delimited JSON-RPC-style messages over stdio
- Tool count: 41
- Storage: SQLite with schema version 2 migrations
- Network scope: `127.0.0.1` only

## Automated coverage

The Python suite verifies:

- migration idempotence and existing-data preservation;
- deck, card, folder, star, ordering, search, duplication, and combination behavior;
- strict, moderate, and relaxed grading plus alternate answers and user overrides;
- multiple-choice-only adaptive Learn queues, configurable Learn goals, two-correct Write/Spell completion, and session resume;
- Test distractors, mixed selected formats, generated true/false statements, scoring, and results;
- spaced-repetition intervals, due cards, mastery, accuracy, study time, streak inputs, most-missed cards, test history, and mode completion;
- Match score, penalty, personal-best, insufficient-card, and no-mastery-change rules;
- JSON, CSV, and separated-text preview/import/export, invalid-import rollback, and media validation;
- REST success and validation-error envelopes;
- all MCP input schemas, representative success/failure calls, unknown tools, lifecycle idempotence, and stale/unowned PID protection.

The Chromium suite verifies a real rendered application through deck creation, inline Front/Back card entry and autosave persistence, an empty mode, six-card study content, Flashcards, Learn refresh resume, Write, Spell, Test, Match, Progress, desktop layout, tablet layout, exact 390 CSS-pixel layout, touch-sized mobile navigation, overflow, and page errors.

## Manual Chrome pass

The release candidate was exercised visibly in Chrome through:

- deck creation, edit, star, duplication, and text-import preview/commit;
- Flashcards flip and review persistence;
- Learn multiple-choice-only flow across consecutive questions and refresh resume;
- Write correction and “I was correct” override;
- Spell speech controls and character-level feedback;
- mixed Test generation, submission, score, and answer review;
- Match mistake penalty, completion, and personal best;
- folder creation and deck assignment;
- expanded Progress history;
- desktop and exact 390 CSS-pixel viewport checks with no horizontal overflow;
- server stop/start with decks and sessions preserved.

Screenshots are stored in `docs/screenshots/`.

## Commands

```powershell
python -m compileall -q local_study_app
python -m pytest -q
python -m local_study_app.mcp_server
```

GitHub Actions repeats unit/MCP checks across Python 3.9, 3.11, and 3.12, runs Chromium separately, and runs Gitleaks against repository history.
