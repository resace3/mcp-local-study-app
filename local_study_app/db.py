"""SQLite storage and forward-only, idempotent migrations."""
import datetime
import json
import os
import sqlite3
from pathlib import Path

APP_VERSION = "2.0.0"
DATA = Path(os.environ.get("STUDY_DATA_DIR", Path(os.environ.get("LOCALAPPDATA", Path.home())) / "local-study-app"))
DB = DATA / "study.db"
MEDIA = DATA / "media"
EXPORTS = DATA / "exports"
STATE = DATA / "server-state.json"
LOGS = DATA / "logs"


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def conn():
    DATA.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DB), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


CARD_COLUMNS = {
    "position": "INTEGER NOT NULL DEFAULT 0",
    "term_language": "TEXT NOT NULL DEFAULT 'auto'",
    "definition_language": "TEXT NOT NULL DEFAULT 'auto'",
    "alternate_answers": "TEXT NOT NULL DEFAULT '[]'",
    "image_path": "TEXT NOT NULL DEFAULT ''",
    "starred": "INTEGER NOT NULL DEFAULT 0",
    "correct_count": "INTEGER NOT NULL DEFAULT 0",
    "incorrect_count": "INTEGER NOT NULL DEFAULT 0",
    "last_reviewed_at": "TEXT",
    "created_at": "TEXT",
    "updated_at": "TEXT",
}

DECK_COLUMNS = {
    "term_language": "TEXT NOT NULL DEFAULT 'auto'",
    "definition_language": "TEXT NOT NULL DEFAULT 'auto'",
    "draft": "INTEGER NOT NULL DEFAULT 0",
    "updated_at": "TEXT",
}


def _add_columns(connection, table, columns):
    existing = {row[1] for row in connection.execute("PRAGMA table_info(%s)" % table)}
    for name, declaration in columns.items():
        if name not in existing:
            connection.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, declaration))


def init_db():
    DATA.mkdir(parents=True, exist_ok=True)
    MEDIA.mkdir(parents=True, exist_ok=True)
    EXPORTS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    with conn() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta(version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS decks(
                id INTEGER PRIMARY KEY,
                title TEXT UNIQUE NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                term_language TEXT NOT NULL DEFAULT 'auto',
                definition_language TEXT NOT NULL DEFAULT 'auto',
                draft INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS cards(
                id INTEGER PRIMARY KEY,
                deck_id INTEGER NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                front TEXT NOT NULL,
                back TEXT NOT NULL,
                hint TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '',
                english TEXT NOT NULL DEFAULT '',
                spanish TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'written',
                options TEXT NOT NULL DEFAULT '[]',
                explanation TEXT NOT NULL DEFAULT '',
                term_language TEXT NOT NULL DEFAULT 'auto',
                definition_language TEXT NOT NULL DEFAULT 'auto',
                alternate_answers TEXT NOT NULL DEFAULT '[]',
                image_path TEXT NOT NULL DEFAULT '',
                starred INTEGER NOT NULL DEFAULT 0,
                due_at TEXT,
                ease REAL NOT NULL DEFAULT 2.5,
                interval INTEGER NOT NULL DEFAULT 0,
                successes INTEGER NOT NULL DEFAULT 0,
                lapses INTEGER NOT NULL DEFAULT 0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                incorrect_count INTEGER NOT NULL DEFAULT 0,
                last_reviewed_at TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS folders(
                id INTEGER PRIMARY KEY,
                title TEXT UNIQUE NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS folder_decks(
                folder_id INTEGER NOT NULL,
                deck_id INTEGER NOT NULL,
                PRIMARY KEY(folder_id, deck_id)
            );
            CREATE TABLE IF NOT EXISTS study_sessions(
                id INTEGER PRIMARY KEY,
                deck_id INTEGER,
                mode TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                options TEXT NOT NULL DEFAULT '{}',
                queue TEXT NOT NULL DEFAULT '[]',
                state TEXT NOT NULL DEFAULT '{}',
                correct INTEGER NOT NULL DEFAULT 0,
                incorrect INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS session_answers(
                id INTEGER PRIMARY KEY,
                session_id INTEGER NOT NULL,
                card_id INTEGER NOT NULL,
                prompt TEXT NOT NULL,
                response TEXT NOT NULL,
                expected TEXT NOT NULL,
                correct INTEGER NOT NULL,
                overridden INTEGER NOT NULL DEFAULT 0,
                elapsed_ms INTEGER NOT NULL DEFAULT 0,
                answered_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reviews(
                id INTEGER PRIMARY KEY,
                card_id INTEGER,
                session_id INTEGER,
                mode TEXT NOT NULL DEFAULT 'flashcards',
                rating TEXT NOT NULL,
                response TEXT NOT NULL DEFAULT '',
                reviewed_at TEXT NOT NULL,
                correct INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS activity(
                id INTEGER PRIMARY KEY,
                kind TEXT NOT NULL,
                detail TEXT NOT NULL,
                deck_id INTEGER,
                happened_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS match_scores(
                id INTEGER PRIMARY KEY,
                deck_id INTEGER NOT NULL,
                elapsed_ms INTEGER NOT NULL,
                mistakes INTEGER NOT NULL DEFAULT 0,
                played_at TEXT NOT NULL
            );
            """
        )
        _add_columns(connection, "decks", DECK_COLUMNS)
        _add_columns(connection, "cards", CARD_COLUMNS)
        _add_columns(connection, "reviews", {"session_id": "INTEGER", "mode": "TEXT NOT NULL DEFAULT 'flashcards'", "response": "TEXT NOT NULL DEFAULT ''"})
        _add_columns(connection, "activity", {"deck_id": "INTEGER"})
        version = connection.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
        if version:
            connection.execute("UPDATE schema_meta SET version=2")
        else:
            connection.execute("INSERT INTO schema_meta(version) VALUES(2)")
        timestamp = utcnow()
        connection.execute("UPDATE decks SET updated_at=COALESCE(updated_at, created_at)")
        connection.execute("UPDATE cards SET created_at=COALESCE(created_at, ?), updated_at=COALESCE(updated_at, ?)", (timestamp, timestamp))
        seed(connection)


def seed(connection):
    if connection.execute("SELECT COUNT(*) FROM decks").fetchone()[0]:
        return
    timestamp = utcnow()
    decks = [
        ("Spanish MTEL Practice", "Bilingual vocabulary and classroom-language practice.", "es", "en"),
        ("Biology Basics", "A quick tour of cells, genetics, and living systems.", "en", "en"),
    ]
    spanish = [
        ("¿Cómo estás?", "How are you?", "A common greeting.", "greetings", "written", []),
        ("¿Qué significa casa?", "House", "Think of a place to live.", "vocabulary", "multiple_choice", ["House", "Car", "Book"]),
        ("El sol es una estrella.", "True", "", "science", "true_false", ["True", "False"]),
        ("Buenos días", "Good morning", "Used before noon.", "greetings", "written", []),
        ("¿Dónde está la biblioteca?", "Where is the library?", "", "travel", "written", []),
        ("Gracias", "Thank you", "", "greetings", "written", []),
        ("Rojo", "Red", "A color.", "colors", "written", []),
        ("Uno, dos, tres", "One, two, three", "", "numbers", "written", []),
        ("¿Qué hora es?", "What time is it?", "", "questions", "written", []),
        ("Amigo", "Friend", "A person you know well.", "people", "written", []),
        ("La biblioteca está cerca.", "The library is nearby.", "", "travel", "written", []),
        ("¿Cuál es tu nombre?", "What is your name?", "", "questions", "written", []),
    ]
    biology = [
        ("What is a cell?", "The basic unit of life", "", "cells", "written", []),
        ("Plants make food by photosynthesis.", "True", "", "plants", "true_false", ["True", "False"]),
        ("DNA carries genetic information.", "True", "", "genetics", "true_false", ["True", "False"]),
        ("Which organelle produces most cellular energy?", "Mitochondrion", "The powerhouse of the cell.", "cells", "multiple_choice", ["Mitochondrion", "Nucleus", "Ribosome"]),
        ("What molecule is the main energy currency of a cell?", "ATP", "Three letters.", "cells", "written", []),
        ("Organisms pass traits through genes.", "True", "", "genetics", "true_false", ["True", "False"]),
    ]
    for title, description, term_language, definition_language in decks:
        deck_id = connection.execute(
            "INSERT INTO decks(title,description,term_language,definition_language,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (title, description, term_language, definition_language, timestamp, timestamp),
        ).lastrowid
        source = spanish if title.startswith("Spanish") else biology
        for position, (front, back, hint, tags, kind, options) in enumerate(source):
            connection.execute(
                """INSERT INTO cards(deck_id,position,front,back,hint,tags,kind,options,term_language,definition_language,
                   alternate_answers,due_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (deck_id, position, front, back, hint, tags, kind, json.dumps(options), term_language, definition_language, "[]", timestamp, timestamp, timestamp),
            )


init_db()
