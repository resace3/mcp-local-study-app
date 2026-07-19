"""Application services shared by REST and MCP transports."""
import csv
import datetime
import difflib
import io
import json
import random
import re
import sqlite3
import unicodedata
import uuid
from pathlib import Path

from .db import EXPORTS, MEDIA, conn, utcnow

VALID_MODES = {"flashcards", "learn", "write", "spell", "test"}
VALID_RATINGS = {"again", "hard", "good", "easy"}
VALID_GRADING = {"strict", "moderate", "relaxed"}
VALID_KINDS = {"written", "multiple_choice", "true_false"}


def ok(data=None, summary="Done"):
    return {"success": True, "data": data, "summary": summary, "error": None}


def err(message, code="invalid_request", details=None):
    return {"success": False, "data": None, "summary": "Request failed", "error": {"code": code, "message": message, "details": details or {}}}


def _loads(value, fallback):
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def _card(row):
    value = dict(row)
    value["options"] = _loads(value.get("options"), [])
    value["alternate_answers"] = _loads(value.get("alternate_answers"), [])
    value["starred"] = bool(value.get("starred"))
    attempts = value.get("correct_count", 0) + value.get("incorrect_count", 0)
    value["accuracy"] = round(value.get("correct_count", 0) / attempts * 100, 1) if attempts else 0
    value["mastery"] = "mastered" if value.get("successes", 0) >= 2 or value.get("interval", 0) >= 7 else ("still_learning" if attempts else "not_studied")
    value["image_url"] = "/api/media/%s" % Path(value["image_path"]).name if value.get("image_path") else ""
    return value


def _deck(row, connection):
    value = dict(row)
    stats = connection.execute(
        """SELECT COUNT(*) total, SUM(CASE WHEN starred=1 THEN 1 ELSE 0 END) starred,
           SUM(CASE WHEN successes>=2 OR interval>=7 THEN 1 ELSE 0 END) mastered
           FROM cards WHERE deck_id=?""", (value["id"],),
    ).fetchone()
    value.update(card_count=stats["total"] or 0, starred_count=stats["starred"] or 0, mastered_count=stats["mastered"] or 0)
    value["folder_ids"] = [x[0] for x in connection.execute("SELECT folder_id FROM folder_decks WHERE deck_id=?", (value["id"],))]
    return value


def list_decks(query="", folder_id=None):
    with conn() as connection:
        sql = "SELECT DISTINCT d.* FROM decks d"
        params = []
        where = []
        if folder_id is not None:
            sql += " JOIN folder_decks fd ON fd.deck_id=d.id"
            where.append("fd.folder_id=?")
            params.append(folder_id)
        if query:
            sql += " LEFT JOIN cards c ON c.deck_id=d.id"
            where.append("(d.title LIKE ? OR d.description LIKE ? OR c.front LIKE ? OR c.back LIKE ? OR c.tags LIKE ?)")
            params.extend(["%%%s%%" % query] * 5)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY d.updated_at DESC, d.id DESC"
        return ok([_deck(row, connection) for row in connection.execute(sql, params)], "Decks loaded")


def get_deck(deck_id):
    with conn() as connection:
        row = connection.execute("SELECT * FROM decks WHERE id=?", (deck_id,)).fetchone()
        return ok(_deck(row, connection), "Deck loaded") if row else err("Deck not found", "not_found")


def create_deck(title, description="", term_language="auto", definition_language="auto", draft=False):
    title = (title or "").strip()
    if not title:
        return err("Title cannot be blank", details={"field": "title"})
    if len(title) > 160:
        return err("Title must be 160 characters or fewer", details={"field": "title"})
    timestamp = utcnow()
    try:
        with conn() as connection:
            deck_id = connection.execute(
                "INSERT INTO decks(title,description,term_language,definition_language,draft,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (title, description.strip(), term_language, definition_language, int(draft), timestamp, timestamp),
            ).lastrowid
            _activity(connection, "deck_created", title, deck_id)
            return ok({"id": deck_id, "title": title}, "Deck created")
    except sqlite3.IntegrityError:
        return err("A deck with that title already exists", "duplicate", {"field": "title"})


def update_deck(deck_id, title=None, description=None, term_language=None, definition_language=None, draft=None):
    values = {"title": title, "description": description, "term_language": term_language, "definition_language": definition_language, "draft": int(draft) if draft is not None else None}
    if title is not None:
        values["title"] = title.strip()
        if not values["title"]:
            return err("Title cannot be blank", details={"field": "title"})
    pairs = [(key, value) for key, value in values.items() if value is not None]
    if not pairs:
        return err("No fields to update")
    try:
        with conn() as connection:
            params = [value for _, value in pairs] + [utcnow(), deck_id]
            count = connection.execute("UPDATE decks SET %s,updated_at=? WHERE id=?" % ",".join("%s=?" % key for key, _ in pairs), params).rowcount
            return ok({"id": deck_id}, "Deck updated") if count else err("Deck not found", "not_found")
    except sqlite3.IntegrityError:
        return err("A deck with that title already exists", "duplicate")


def delete_deck(deck_id):
    with conn() as connection:
        row = connection.execute("SELECT title FROM decks WHERE id=?", (deck_id,)).fetchone()
        if not row:
            return err("Deck not found", "not_found")
        card_ids = [item[0] for item in connection.execute("SELECT id FROM cards WHERE deck_id=?", (deck_id,))]
        for card_id in card_ids:
            connection.execute("DELETE FROM session_answers WHERE card_id=?", (card_id,))
            connection.execute("DELETE FROM reviews WHERE card_id=?", (card_id,))
        connection.execute("DELETE FROM study_sessions WHERE deck_id=?", (deck_id,))
        connection.execute("DELETE FROM match_scores WHERE deck_id=?", (deck_id,))
        connection.execute("DELETE FROM folder_decks WHERE deck_id=?", (deck_id,))
        connection.execute("DELETE FROM cards WHERE deck_id=?", (deck_id,))
        connection.execute("DELETE FROM decks WHERE id=?", (deck_id,))
        _activity(connection, "deck_deleted", row["title"], None)
        return ok({"deleted": 1}, "Deck deleted")


def duplicate_deck(deck_id, title=None):
    source = get_deck(deck_id)
    if not source["success"]:
        return source
    target_title = title or source["data"]["title"] + " Copy"
    created = create_deck(target_title, source["data"]["description"], source["data"]["term_language"], source["data"]["definition_language"])
    if not created["success"]:
        return created
    cards = list_cards(deck_id)["data"]
    bulk = create_flashcards_bulk(created["data"]["id"], cards)
    if not bulk["success"]:
        delete_deck(created["data"]["id"])
        return bulk
    return ok({"id": created["data"]["id"], "title": target_title, "card_count": len(cards)}, "Deck duplicated")


def combine_decks(deck_ids, title=None, persist=True):
    unique_ids = list(dict.fromkeys(int(x) for x in deck_ids))
    if len(unique_ids) < 2:
        return err("Choose at least two decks to combine")
    decks = [get_deck(x) for x in unique_ids]
    missing = [unique_ids[i] for i, item in enumerate(decks) if not item["success"]]
    if missing:
        return err("One or more decks were not found", "not_found", {"deck_ids": missing})
    cards = []
    for deck_id in unique_ids:
        cards.extend(list_cards(deck_id)["data"])
    if not persist:
        return ok({"deck_ids": unique_ids, "cards": cards, "title": title or "Combined study session"}, "Temporary combination ready")
    result = create_deck(title or " + ".join(x["data"]["title"] for x in decks))
    if not result["success"]:
        return result
    create_flashcards_bulk(result["data"]["id"], cards)
    return ok({"id": result["data"]["id"], "card_count": len(cards)}, "Combined deck created")


def list_cards(deck_id, query="", starred=None, mastery=None):
    sql = "SELECT * FROM cards WHERE deck_id=?"
    params = [deck_id]
    if query:
        sql += " AND (front LIKE ? OR back LIKE ? OR tags LIKE ? OR hint LIKE ?)"
        params.extend(["%%%s%%" % query] * 4)
    if starred is not None:
        sql += " AND starred=?"
        params.append(int(starred))
    if mastery == "mastered":
        sql += " AND (successes>=2 OR interval>=7)"
    elif mastery == "still_learning":
        sql += " AND (correct_count+incorrect_count)>0 AND successes<2 AND interval<7"
    elif mastery == "not_studied":
        sql += " AND (correct_count+incorrect_count)=0"
    sql += " ORDER BY position,id"
    with conn() as connection:
        if not connection.execute("SELECT 1 FROM decks WHERE id=?", (deck_id,)).fetchone():
            return err("Deck not found", "not_found")
        return ok([_card(row) for row in connection.execute(sql, params)], "Cards loaded")


def get_card(card_id):
    with conn() as connection:
        row = connection.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        return ok(_card(row), "Card loaded") if row else err("Card not found", "not_found")


def _validate_card(front, back, kind, options):
    if not (front or "").strip() or not (back or "").strip():
        return "Front and back are required"
    if kind not in VALID_KINDS:
        return "Card type must be written, multiple_choice, or true_false"
    if kind == "multiple_choice" and len(set(options or [])) < 3:
        return "Multiple-choice cards need at least three unique options"
    return None


def create_card(deck_id, front, back, hint="", tags="", english="", spanish="", kind="written", options=None, explanation="", alternate_answers=None, term_language="auto", definition_language="auto", image_path="", starred=False, position=None, **_ignored):
    options = options or []
    problem = _validate_card(front, back, kind, options)
    if problem:
        return err(problem)
    with conn() as connection:
        if not connection.execute("SELECT 1 FROM decks WHERE id=?", (deck_id,)).fetchone():
            return err("Deck not found", "not_found")
        if position is None:
            position = connection.execute("SELECT COALESCE(MAX(position),-1)+1 FROM cards WHERE deck_id=?", (deck_id,)).fetchone()[0]
        timestamp = utcnow()
        card_id = connection.execute(
            """INSERT INTO cards(deck_id,position,front,back,hint,tags,english,spanish,kind,options,explanation,
               alternate_answers,term_language,definition_language,image_path,starred,due_at,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (deck_id, position, front.strip(), back.strip(), hint.strip(), tags.strip(), english.strip(), spanish.strip(), kind, json.dumps(options, ensure_ascii=False), explanation.strip(), json.dumps(alternate_answers or [], ensure_ascii=False), term_language, definition_language, image_path, int(starred), timestamp, timestamp, timestamp),
        ).lastrowid
        connection.execute("UPDATE decks SET updated_at=? WHERE id=?", (timestamp, deck_id))
        return ok({"id": card_id}, "Card created")


def create_flashcards_bulk(deck_id, cards):
    if not isinstance(cards, list) or not cards:
        return err("Cards must be a non-empty list")
    normalized = []
    for index, item in enumerate(cards):
        if not isinstance(item, dict):
            return err("Every card must be an object", details={"index": index})
        options = item.get("options") or []
        if isinstance(options, str):
            options = _loads(options, [x.strip() for x in options.split("|") if x.strip()])
        problem = _validate_card(item.get("front"), item.get("back"), item.get("kind", "written"), options)
        if problem:
            return err(problem, details={"index": index})
        copy = dict(item)
        copy["options"] = options
        normalized.append(copy)
    created = []
    for item in normalized:
        result = create_card(deck_id, **{key: item.get(key) for key in ["front", "back", "hint", "tags", "english", "spanish", "kind", "options", "explanation", "alternate_answers", "term_language", "definition_language", "image_path", "starred"] if item.get(key) is not None})
        if not result["success"]:
            return result
        created.append(result["data"]["id"])
    return ok({"created": len(created), "ids": created}, "%d cards created" % len(created))


def update_card(card_id, **fields):
    allowed = {"front", "back", "hint", "tags", "english", "spanish", "kind", "options", "explanation", "alternate_answers", "term_language", "definition_language", "image_path", "starred", "position"}
    values = []
    assignments = []
    for key in allowed:
        if key in fields and fields[key] is not None:
            value = fields[key]
            if key in {"options", "alternate_answers"}:
                value = json.dumps(value, ensure_ascii=False)
            elif key == "starred":
                value = int(value)
            assignments.append("%s=?" % key)
            values.append(value)
    if not assignments:
        return err("No fields to update")
    assignments.append("updated_at=?")
    values.extend([utcnow(), card_id])
    try:
        with conn() as connection:
            count = connection.execute("UPDATE cards SET %s WHERE id=?" % ",".join(assignments), values).rowcount
            return ok({"id": card_id}, "Card updated") if count else err("Card not found", "not_found")
    except sqlite3.IntegrityError as exc:
        return err("Card could not be updated", details={"reason": str(exc)})


def delete_card(card_id):
    with conn() as connection:
        row = connection.execute("SELECT deck_id,image_path FROM cards WHERE id=?", (card_id,)).fetchone()
        if not row:
            return err("Card not found", "not_found")
        connection.execute("DELETE FROM session_answers WHERE card_id=?", (card_id,))
        connection.execute("DELETE FROM reviews WHERE card_id=?", (card_id,))
        connection.execute("DELETE FROM cards WHERE id=?", (card_id,))
        _normalize_positions(connection, row["deck_id"])
        return ok({"deleted": 1}, "Card deleted")


def reorder_cards(deck_id, card_ids):
    with conn() as connection:
        existing = [row[0] for row in connection.execute("SELECT id FROM cards WHERE deck_id=? ORDER BY position,id", (deck_id,))]
        if sorted(existing) != sorted(int(x) for x in card_ids):
            return err("Card order must include every card in the deck exactly once")
        for position, card_id in enumerate(card_ids):
            connection.execute("UPDATE cards SET position=?,updated_at=? WHERE id=?", (position, utcnow(), card_id))
        return ok({"deck_id": deck_id, "card_ids": card_ids}, "Cards reordered")


def search_cards(query, deck_id=None):
    if not (query or "").strip():
        return err("Search query cannot be blank")
    with conn() as connection:
        sql = "SELECT c.*,d.title deck_title FROM cards c JOIN decks d ON d.id=c.deck_id WHERE (c.front LIKE ? OR c.back LIKE ? OR c.tags LIKE ? OR c.hint LIKE ?)"
        params = ["%%%s%%" % query] * 4
        if deck_id is not None:
            sql += " AND c.deck_id=?"
            params.append(deck_id)
        sql += " ORDER BY d.title,c.position LIMIT 200"
        return ok([_card(row) for row in connection.execute(sql, params)], "Search complete")


def toggle_star(card_id, starred=None):
    with conn() as connection:
        row = connection.execute("SELECT starred FROM cards WHERE id=?", (card_id,)).fetchone()
        if not row:
            return err("Card not found", "not_found")
        value = int(not row["starred"] if starred is None else starred)
        connection.execute("UPDATE cards SET starred=?,updated_at=? WHERE id=?", (value, utcnow(), card_id))
        return ok({"id": card_id, "starred": bool(value)}, "Card starred" if value else "Card unstarred")


def list_folders():
    with conn() as connection:
        rows = []
        for row in connection.execute("SELECT * FROM folders ORDER BY title"):
            item = dict(row)
            item["deck_count"] = connection.execute("SELECT COUNT(*) FROM folder_decks WHERE folder_id=?", (row["id"],)).fetchone()[0]
            rows.append(item)
        return ok(rows, "Folders loaded")


def create_folder(title, description=""):
    title = (title or "").strip()
    if not title:
        return err("Folder title cannot be blank")
    try:
        with conn() as connection:
            timestamp = utcnow()
            folder_id = connection.execute("INSERT INTO folders(title,description,created_at,updated_at) VALUES(?,?,?,?)", (title, description.strip(), timestamp, timestamp)).lastrowid
            return ok({"id": folder_id, "title": title}, "Folder created")
    except sqlite3.IntegrityError:
        return err("A folder with that title already exists", "duplicate")


def update_folder(folder_id, title=None, description=None):
    pairs = [(k, v.strip()) for k, v in (("title", title), ("description", description)) if v is not None]
    if not pairs or any(k == "title" and not v for k, v in pairs):
        return err("Provide a valid title or description")
    try:
        with conn() as connection:
            values = [v for _, v in pairs] + [utcnow(), folder_id]
            count = connection.execute("UPDATE folders SET %s,updated_at=? WHERE id=?" % ",".join("%s=?" % k for k, _ in pairs), values).rowcount
            return ok({"id": folder_id}, "Folder updated") if count else err("Folder not found", "not_found")
    except sqlite3.IntegrityError:
        return err("A folder with that title already exists", "duplicate")


def delete_folder(folder_id):
    with conn() as connection:
        connection.execute("DELETE FROM folder_decks WHERE folder_id=?", (folder_id,))
        count = connection.execute("DELETE FROM folders WHERE id=?", (folder_id,)).rowcount
        return ok({"deleted": count}, "Folder deleted") if count else err("Folder not found", "not_found")


def set_folder_deck(folder_id, deck_id, included=True):
    with conn() as connection:
        if not connection.execute("SELECT 1 FROM folders WHERE id=?", (folder_id,)).fetchone():
            return err("Folder not found", "not_found")
        if not connection.execute("SELECT 1 FROM decks WHERE id=?", (deck_id,)).fetchone():
            return err("Deck not found", "not_found")
        if included:
            connection.execute("INSERT OR IGNORE INTO folder_decks(folder_id,deck_id) VALUES(?,?)", (folder_id, deck_id))
        else:
            connection.execute("DELETE FROM folder_decks WHERE folder_id=? AND deck_id=?", (folder_id, deck_id))
        return ok({"folder_id": folder_id, "deck_id": deck_id, "included": included}, "Folder membership updated")


def normalize_answer(value, level="strict"):
    text = unicodedata.normalize("NFKC", value or "").casefold().strip()
    text = re.sub(r"^[\W_]+|[\W_]+$", "", text)
    text = re.sub(r"\s+", " ", text)
    if level in {"moderate", "relaxed"}:
        text = "".join(char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char))
    if level == "relaxed":
        text = " ".join(sorted(re.findall(r"[\w']+", text)))
    return text


def grade_answer(response, expected, alternates=None, level="strict"):
    if level not in VALID_GRADING:
        level = "strict"
    candidate = normalize_answer(response, level)
    answers = [expected] + list(alternates or [])
    normalized = [normalize_answer(item, level) for item in answers]
    if candidate in normalized:
        return True
    if level == "moderate":
        return any(difflib.SequenceMatcher(None, candidate, answer).ratio() >= 0.88 for answer in normalized if answer)
    if level == "relaxed":
        return any(difflib.SequenceMatcher(None, candidate, answer).ratio() >= 0.82 for answer in normalized if answer)
    return False


def start_session(deck_id, mode="learn", options=None):
    if mode not in VALID_MODES:
        return err("Unsupported study mode")
    options = dict(options or {})
    cards_result = list_cards(deck_id, starred=True if options.get("starred_only") else None, mastery=options.get("mastery"))
    if not cards_result["success"]:
        return cards_result
    cards = cards_result["data"]
    if not cards:
        return err("No cards match the selected study options", "empty")
    if options.get("adaptive", True):
        cards.sort(key=lambda item: (item["mastery"] == "mastered", -item["incorrect_count"], item["correct_count"], item["position"]))
    queue = [item["id"] for item in cards]
    if options.get("shuffle", False):
        random.shuffle(queue)
    state = {"cursor": 0, "per_card": {}, "answered": 0}
    timestamp = utcnow()
    with conn() as connection:
        session_id = connection.execute(
            "INSERT INTO study_sessions(deck_id,mode,options,queue,state,started_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (deck_id, mode, json.dumps(options), json.dumps(queue), json.dumps(state), timestamp, timestamp),
        ).lastrowid
        _activity(connection, "session_started", mode, deck_id)
    return get_session(session_id)


def get_session(session_id):
    with conn() as connection:
        row = connection.execute("SELECT * FROM study_sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            return err("Study session not found", "not_found")
        value = dict(row)
        value["options"] = _loads(value["options"], {})
        value["queue"] = _loads(value["queue"], [])
        value["state"] = _loads(value["state"], {})
        cursor = value["state"].get("cursor", 0)
        value["current_card"] = None
        if value["status"] == "active" and cursor < len(value["queue"]):
            card_row = connection.execute("SELECT * FROM cards WHERE id=?", (value["queue"][cursor],)).fetchone()
            value["current_card"] = _card(card_row) if card_row else None
        value["progress_percent"] = round(cursor / max(len(value["queue"]), 1) * 100)
        return ok(value, "Session loaded")


def answer_session(session_id, response="", card_id=None, override=False, elapsed_ms=0):
    with conn() as connection:
        row = connection.execute("SELECT * FROM study_sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            return err("Study session not found", "not_found")
        if row["status"] != "active":
            return err("Study session is already complete", "conflict")
        options = _loads(row["options"], {})
        queue = _loads(row["queue"], [])
        state = _loads(row["state"], {})
        cursor = state.get("cursor", 0)
        if cursor >= len(queue):
            return err("No current question", "conflict")
        expected_card_id = queue[cursor]
        if card_id is not None and int(card_id) != expected_card_id:
            return err("Answer does not match the current card", "conflict")
        card_row = connection.execute("SELECT * FROM cards WHERE id=?", (expected_card_id,)).fetchone()
        if not card_row:
            return err("Card not found", "not_found")
        item = _card(card_row)
        reverse = options.get("answer_with") == "term"
        prompt, expected = (item["back"], item["front"]) if reverse else (item["front"], item["back"])
        correct = bool(override) or grade_answer(response, expected, item["alternate_answers"], options.get("grading", "strict"))
        connection.execute(
            "INSERT INTO session_answers(session_id,card_id,prompt,response,expected,correct,overridden,elapsed_ms,answered_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (session_id, expected_card_id, prompt, response, expected, int(correct), int(override), max(0, int(elapsed_ms)), utcnow()),
        )
        mode = row["mode"]
        state["answered"] = state.get("answered", 0) + 1
        progress = state.setdefault("per_card", {}).setdefault(str(expected_card_id), {"correct": 0, "incorrect": 0})
        progress["correct" if correct else "incorrect"] += 1
        target = max(1, min(int(options.get("target_repetitions", 2)), 5)) if mode == "learn" else (2 if mode in {"write", "spell"} else 1)
        if mode != "test" and (not correct or progress["correct"] < target):
            queue.append(expected_card_id)
        cursor += 1
        state["cursor"] = cursor
        complete = cursor >= len(queue)
        connection.execute(
            "UPDATE study_sessions SET queue=?,state=?,correct=correct+?,incorrect=incorrect+?,status=?,updated_at=?,completed_at=? WHERE id=?",
            (json.dumps(queue), json.dumps(state), int(correct), int(not correct), "complete" if complete else "active", utcnow(), utcnow() if complete else None, session_id),
        )
        _record_learning(connection, expected_card_id, mode, correct, session_id, response)
        if complete:
            _activity(connection, "session_completed", mode, row["deck_id"])
        feedback = {"card_id": expected_card_id, "prompt": prompt, "correct": correct, "expected": expected, "response": response, "explanation": item["explanation"], "complete": complete}
    result = get_session(session_id)
    feedback["session"] = result["data"]
    return ok(feedback, "Correct" if correct else "Keep learning")


def override_last_answer(session_id):
    """Mark the most recent incorrect session answer correct and remove its retry."""
    with conn() as connection:
        session = connection.execute("SELECT * FROM study_sessions WHERE id=?", (session_id,)).fetchone()
        answer = connection.execute("SELECT * FROM session_answers WHERE session_id=? ORDER BY id DESC LIMIT 1", (session_id,)).fetchone()
        if not session or not answer:
            return err("No answer is available to override", "not_found")
        if answer["correct"]:
            return ok({"session_id": session_id, "already_correct": True}, "Answer was already correct")
        connection.execute("UPDATE session_answers SET correct=1,overridden=1 WHERE id=?", (answer["id"],))
        connection.execute("UPDATE study_sessions SET correct=correct+1,incorrect=CASE WHEN incorrect>0 THEN incorrect-1 ELSE 0 END,updated_at=? WHERE id=?", (utcnow(), session_id))
        connection.execute("UPDATE cards SET correct_count=correct_count+1,incorrect_count=CASE WHEN incorrect_count>0 THEN incorrect_count-1 ELSE 0 END,successes=successes+1,lapses=CASE WHEN lapses>0 THEN lapses-1 ELSE 0 END,updated_at=? WHERE id=?", (utcnow(), answer["card_id"]))
        review = connection.execute("SELECT id FROM reviews WHERE session_id=? AND card_id=? ORDER BY id DESC LIMIT 1", (session_id, answer["card_id"])).fetchone()
        if review:
            connection.execute("UPDATE reviews SET correct=1,rating='good' WHERE id=?", (review["id"],))
        queue = _loads(session["queue"], [])
        state = _loads(session["state"], {})
        cursor = state.get("cursor", 0)
        try:
            retry_index = queue.index(answer["card_id"], cursor)
            queue.pop(retry_index)
        except ValueError:
            pass
        per_card = state.get("per_card", {}).get(str(answer["card_id"]), {})
        per_card["incorrect"] = max(0, per_card.get("incorrect", 0) - 1)
        per_card["correct"] = per_card.get("correct", 0) + 1
        complete = cursor >= len(queue)
        connection.execute("UPDATE study_sessions SET queue=?,state=?,status=?,completed_at=? WHERE id=?", (json.dumps(queue), json.dumps(state), "complete" if complete else "active", utcnow() if complete else None, session_id))
    return ok({"session_id": session_id, "session": get_session(session_id)["data"]}, "Answer marked correct")


def generate_quiz(deck_id, limit=10, types=None, starred_only=False):
    cards_result = list_cards(deck_id, starred=True if starred_only else None)
    if not cards_result["success"]:
        return cards_result
    cards = cards_result["data"]
    if not cards:
        return err("This deck has no cards", "empty")
    if types is None:
        types = ["multiple_choice", "true_false", "written"]
    types = [value for value in types if value in {"multiple_choice", "true_false", "written"}]
    if not types:
        return err("Choose at least one supported question type")
    limit = max(1, min(int(limit), len(cards)))
    chosen = random.sample(cards, limit)
    answers = list(dict.fromkeys(x["back"] for x in cards))
    questions = []
    warning = None
    for index, item in enumerate(chosen):
        qtype = types[index % len(types)]
        question = item["front"]
        answer = item["back"]
        if qtype == "multiple_choice":
            distractors = [x for x in answers if x != item["back"]]
            random.shuffle(distractors)
            options = list(dict.fromkeys([item["back"]] + distractors[:3]))
            if len(options) < 3:
                qtype = "written"
                warning = "Some multiple-choice questions became written questions because the deck has too few unique answers."
            else:
                random.shuffle(options)
        elif qtype == "true_false":
            options = ["True", "False"]
            distractors = [x for x in answers if x != item["back"]]
            truthful = not distractors or random.choice([True, False])
            shown_answer = item["back"] if truthful else random.choice(distractors)
            question = "%s — %s" % (item["front"], shown_answer)
            answer = "True" if truthful else "False"
        else:
            options = []
        questions.append({"card_id": item["id"], "type": qtype, "question": question, "options": options, "answer": answer, "explanation": item["explanation"]})
    timestamp = utcnow()
    state = {"questions": questions}
    with conn() as connection:
        session_id = connection.execute(
            "INSERT INTO study_sessions(deck_id,mode,options,queue,state,started_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (deck_id, "test", json.dumps({"types": types, "starred_only": starred_only}), json.dumps([x["card_id"] for x in questions]), json.dumps(state), timestamp, timestamp),
        ).lastrowid
        _activity(connection, "test_started", "%d questions" % len(questions), deck_id)
    safe_questions = [{key: value for key, value in question.items() if key != "answer"} for question in questions]
    return ok({"session_id": session_id, "questions": safe_questions, "warning": warning}, "Test generated")


def submit_quiz(session_id, answers, grading="strict"):
    with conn() as connection:
        row = connection.execute("SELECT * FROM study_sessions WHERE id=? AND mode='test'", (session_id,)).fetchone()
        if not row:
            return err("Test not found", "not_found")
        if row["status"] == "complete":
            return get_quiz_results(session_id)
        questions = _loads(row["state"], {}).get("questions", [])
        review = []
        correct_count = 0
        answer_map = {str(k): v for k, v in (answers or {}).items()}
        for question in questions:
            response = str(answer_map.get(str(question["card_id"]), ""))
            correct = grade_answer(response, question["answer"], [], grading)
            correct_count += int(correct)
            review.append({"card_id": question["card_id"], "question": question["question"], "response": response, "expected": question["answer"], "correct": correct, "explanation": question["explanation"]})
            connection.execute("INSERT INTO session_answers(session_id,card_id,prompt,response,expected,correct,answered_at) VALUES(?,?,?,?,?,?,?)", (session_id, question["card_id"], question["question"], response, question["answer"], int(correct), utcnow()))
            _record_learning(connection, question["card_id"], "test", correct, session_id, response)
        state = {"questions": questions, "review": review, "score": round(correct_count / len(questions) * 100) if questions else 0}
        connection.execute("UPDATE study_sessions SET state=?,correct=?,incorrect=?,status='complete',updated_at=?,completed_at=? WHERE id=?", (json.dumps(state), correct_count, len(questions) - correct_count, utcnow(), utcnow(), session_id))
        _activity(connection, "test_completed", "%d%%" % state["score"], row["deck_id"])
    return get_quiz_results(session_id)


def get_quiz_results(session_id):
    with conn() as connection:
        row = connection.execute("SELECT * FROM study_sessions WHERE id=? AND mode='test'", (session_id,)).fetchone()
        if not row:
            return err("Test not found", "not_found")
        state = _loads(row["state"], {})
        return ok({"session_id": session_id, "complete": row["status"] == "complete", "score": state.get("score"), "correct": row["correct"], "incorrect": row["incorrect"], "review": state.get("review", [])}, "Test results loaded")


def record_review(card_id, rating, session_id=None):
    if rating not in VALID_RATINGS:
        return err("Rating must be again, hard, good, or easy")
    intervals = {"again": 0, "hard": 1, "good": 3, "easy": 7}
    with conn() as connection:
        row = connection.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        if not row:
            return err("Card not found", "not_found")
        success = rating != "again"
        base = intervals[rating]
        interval = base if row["interval"] <= 0 else max(base, round(row["interval"] * ({"hard": 1.2, "good": row["ease"], "easy": row["ease"] + 1}.get(rating, 0))))
        due_at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=interval)).isoformat()
        ease = max(1.3, row["ease"] + {"again": -0.25, "hard": -0.15, "good": 0, "easy": 0.15}[rating])
        connection.execute("UPDATE cards SET due_at=?,interval=?,ease=?,successes=successes+?,lapses=lapses+?,correct_count=correct_count+?,incorrect_count=incorrect_count+?,last_reviewed_at=?,updated_at=? WHERE id=?", (due_at, interval, ease, int(success), int(not success), int(success), int(not success), utcnow(), utcnow(), card_id))
        connection.execute("INSERT INTO reviews(card_id,session_id,mode,rating,reviewed_at,correct) VALUES(?,?,?,?,?,?)", (card_id, session_id, "flashcards", rating, utcnow(), int(success)))
        _activity(connection, "card_reviewed", rating, row["deck_id"])
        return ok({"card_id": card_id, "rating": rating, "next_due": due_at, "interval": interval, "mastery": "mastered" if interval >= 7 else "still_learning"}, "Review recorded")


def get_due_cards(deck_id=None, limit=100):
    with conn() as connection:
        sql = "SELECT * FROM cards WHERE due_at IS NULL OR due_at<=?"
        params = [utcnow()]
        if deck_id is not None:
            sql += " AND deck_id=?"
            params.append(deck_id)
        sql += " ORDER BY due_at,position LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        return ok([_card(row) for row in connection.execute(sql, params)], "Due cards loaded")


def record_match_score(deck_id, elapsed_ms, mistakes=0):
    if int(elapsed_ms) <= 0:
        return err("Elapsed time must be positive")
    with conn() as connection:
        if not connection.execute("SELECT 1 FROM decks WHERE id=?", (deck_id,)).fetchone():
            return err("Deck not found", "not_found")
        connection.execute("INSERT INTO match_scores(deck_id,elapsed_ms,mistakes,played_at) VALUES(?,?,?,?)", (deck_id, int(elapsed_ms), max(0, int(mistakes)), utcnow()))
        best = connection.execute("SELECT MIN(elapsed_ms) FROM match_scores WHERE deck_id=?", (deck_id,)).fetchone()[0]
        _activity(connection, "match_completed", "%d ms" % int(elapsed_ms), deck_id)
        return ok({"elapsed_ms": int(elapsed_ms), "mistakes": int(mistakes), "best_ms": best, "new_best": int(elapsed_ms) == best}, "Match score saved")


def get_match_scores(deck_id):
    with conn() as connection:
        rows = [dict(row) for row in connection.execute("SELECT * FROM match_scores WHERE deck_id=? ORDER BY elapsed_ms LIMIT 10", (deck_id,))]
        return ok({"best_ms": rows[0]["elapsed_ms"] if rows else None, "scores": rows}, "Match scores loaded")


def get_progress(deck_id=None):
    with conn() as connection:
        where = " WHERE deck_id=?" if deck_id is not None else ""
        params = (deck_id,) if deck_id is not None else ()
        stats = connection.execute(
            """SELECT COUNT(*) total_cards,
               SUM(CASE WHEN correct_count+incorrect_count=0 THEN 1 ELSE 0 END) not_studied,
               SUM(CASE WHEN correct_count+incorrect_count>0 AND successes<2 AND interval<7 THEN 1 ELSE 0 END) still_learning,
               SUM(CASE WHEN successes>=2 OR interval>=7 THEN 1 ELSE 0 END) mastered,
               SUM(correct_count) correct, SUM(incorrect_count) incorrect
               FROM cards""" + where, params,
        ).fetchone()
        attempts = (stats["correct"] or 0) + (stats["incorrect"] or 0)
        due_count = len(get_due_cards(deck_id, 500)["data"])
        reviews_where = " WHERE c.deck_id=?" if deck_id is not None else ""
        review_dates = [row[0][:10] for row in connection.execute("SELECT DISTINCT r.reviewed_at FROM reviews r JOIN cards c ON c.id=r.card_id" + reviews_where + " ORDER BY r.reviewed_at DESC", params)]
        streak = _streak(review_dates)
        session_where = " WHERE deck_id=?" if deck_id is not None else ""
        sessions = [dict(row) for row in connection.execute("SELECT id,deck_id,mode,status,correct,incorrect,started_at,completed_at FROM study_sessions" + session_where + " ORDER BY started_at DESC LIMIT 20", params)]
        match = [dict(row) for row in connection.execute("SELECT * FROM match_scores" + session_where + " ORDER BY played_at DESC LIMIT 10", params)]
        study_time = connection.execute("SELECT COALESCE(SUM(MAX(0,(julianday(COALESCE(completed_at,updated_at))-julianday(started_at))*86400000)),0) FROM study_sessions" + session_where, params).fetchone()[0]
        missed_where = " WHERE incorrect_count>0" + (" AND deck_id=?" if deck_id is not None else "")
        most_missed = [dict(row) for row in connection.execute("SELECT id,deck_id,front,back,incorrect_count,correct_count FROM cards" + missed_where + " ORDER BY incorrect_count DESC,correct_count ASC LIMIT 10", params)]
        completed_where = " WHERE status='complete'" + (" AND deck_id=?" if deck_id is not None else "")
        mode_completion = {row["mode"]: row["count"] for row in connection.execute("SELECT mode,COUNT(*) count FROM study_sessions" + completed_where + " GROUP BY mode", params)}
        tests_where = " WHERE mode='test' AND status='complete'" + (" AND deck_id=?" if deck_id is not None else "")
        quiz_scores = []
        for row in connection.execute("SELECT id,deck_id,state,completed_at FROM study_sessions" + tests_where + " ORDER BY completed_at DESC LIMIT 10", params):
            state = _loads(row["state"], {})
            quiz_scores.append({"session_id": row["id"], "deck_id": row["deck_id"], "score": state.get("score", 0), "completed_at": row["completed_at"]})
        return ok({"total_cards": stats["total_cards"] or 0, "not_studied": stats["not_studied"] or 0, "still_learning": stats["still_learning"] or 0, "mastered": stats["mastered"] or 0, "due": due_count, "correct": stats["correct"] or 0, "incorrect": stats["incorrect"] or 0, "accuracy": round((stats["correct"] or 0) / attempts * 100, 1) if attempts else 0, "streak": streak, "study_time_ms": round(study_time or 0), "most_missed": most_missed, "quiz_scores": quiz_scores, "mode_completion": mode_completion, "sessions": sessions, "match_scores": match}, "Progress loaded")


def get_recent_activity(limit=20):
    with conn() as connection:
        rows = [dict(row) for row in connection.execute("SELECT a.*,d.title deck_title FROM activity a LEFT JOIN decks d ON d.id=a.deck_id ORDER BY happened_at DESC LIMIT ?", (max(1, min(int(limit), 100)),))]
        return ok(rows, "Recent activity loaded")


def preview_import(payload, fmt="json", term_separator=None, row_separator=None):
    try:
        cards = []
        title = "Imported deck"
        description = ""
        if len(payload.encode("utf-8")) > 2 * 1024 * 1024:
            return err("Import is larger than the 2 MB limit", "too_large")
        if fmt == "json":
            obj = json.loads(payload)
            title = str(obj.get("title") or title)
            description = str(obj.get("description") or "")
            cards = obj.get("cards") or []
        elif fmt == "csv":
            cards = list(csv.DictReader(io.StringIO(payload)))
        elif fmt == "text":
            lines = payload.split(row_separator) if row_separator else payload.splitlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                separator = term_separator
                if not separator:
                    separator = "\t" if "\t" in line else ("," if "," in line else " - ")
                if separator not in line:
                    return err("A row has no recognizable term separator", details={"row": line[:120]})
                front, back = line.split(separator, 1)
                cards.append({"front": front.strip(), "back": back.strip()})
        else:
            return err("Format must be json, csv, or text")
        normalized = []
        for index, item in enumerate(cards):
            if not isinstance(item, dict) or not str(item.get("front") or "").strip() or not str(item.get("back") or "").strip():
                return err("Every imported card needs front and back", details={"index": index})
            options = item.get("options", [])
            if isinstance(options, str):
                options = _loads(options, [x.strip() for x in options.split("|") if x.strip()])
            alternates = item.get("alternate_answers", [])
            if isinstance(alternates, str):
                alternates = _loads(alternates, [x.strip() for x in alternates.split("|") if x.strip()])
            normalized.append({"front": str(item["front"]).strip(), "back": str(item["back"]).strip(), "hint": str(item.get("hint") or ""), "tags": str(item.get("tags") or ""), "kind": str(item.get("kind") or "written"), "options": options, "explanation": str(item.get("explanation") or ""), "alternate_answers": alternates})
        if not normalized:
            return err("Import contains no cards", "empty")
        return ok({"title": title, "description": description, "cards": normalized, "card_count": len(normalized)}, "Import validated")
    except (ValueError, csv.Error, TypeError) as exc:
        return err("Invalid import", details={"reason": str(exc)})


def import_deck(payload, fmt="json", title=None, term_separator=None, row_separator=None):
    preview = preview_import(payload, fmt, term_separator, row_separator)
    if not preview["success"]:
        return preview
    data = preview["data"]
    created = create_deck(title or data["title"], data["description"])
    if not created["success"]:
        return created
    bulk = create_flashcards_bulk(created["data"]["id"], data["cards"])
    if not bulk["success"]:
        delete_deck(created["data"]["id"])
        return bulk
    return ok({"deck_id": created["data"]["id"], "card_count": data["card_count"]}, "Deck imported")


def export_deck(deck_id, fmt="json"):
    deck_result = get_deck(deck_id)
    if not deck_result["success"]:
        return deck_result
    cards = list_cards(deck_id)["data"]
    if fmt == "json":
        content = json.dumps({"format": "local-study-app", "version": 2, "title": deck_result["data"]["title"], "description": deck_result["data"]["description"], "cards": cards}, ensure_ascii=False, indent=2)
        mime, extension = "application/json", "json"
    elif fmt == "csv":
        output = io.StringIO()
        fields = ["front", "back", "hint", "tags", "kind", "options", "explanation", "alternate_answers", "term_language", "definition_language"]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for item in cards:
            row = {key: item.get(key, "") for key in fields}
            row["options"] = "|".join(row["options"])
            row["alternate_answers"] = "|".join(row["alternate_answers"])
            writer.writerow(row)
        content, mime, extension = output.getvalue(), "text/csv", "csv"
    elif fmt == "text":
        content = "\n".join("%s\t%s" % (item["front"], item["back"]) for item in cards)
        mime, extension = "text/plain", "txt"
    else:
        return err("Format must be json, csv, or text")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", deck_result["data"]["title"]).strip("-") or "deck"
    filename = "%s-%s.%s" % (safe_name, uuid.uuid4().hex[:8], extension)
    path = EXPORTS / filename
    path.write_text(content, encoding="utf-8")
    return ok({"format": fmt, "content": content, "mime_type": mime, "filename": filename, "download_url": "/api/exports/%s" % filename}, "%s exported" % fmt.upper())


def save_media(filename, content_type, data):
    allowed = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}
    if content_type not in allowed:
        return err("Only PNG, JPEG, WebP, and GIF images are supported", "unsupported_media")
    if len(data) > 5 * 1024 * 1024:
        return err("Image exceeds the 5 MB limit", "too_large")
    signatures = {"image/png": b"\x89PNG", "image/jpeg": b"\xff\xd8\xff", "image/webp": b"RIFF", "image/gif": b"GIF8"}
    if not data.startswith(signatures[content_type]):
        return err("The uploaded file does not match its image type", "invalid_media")
    stored = uuid.uuid4().hex + allowed[content_type]
    path = MEDIA / stored
    path.write_bytes(data)
    return ok({"filename": stored, "image_path": str(path), "url": "/api/media/%s" % stored}, "Image uploaded")


def _record_learning(connection, card_id, mode, correct, session_id, response):
    timestamp = utcnow()
    connection.execute("UPDATE cards SET correct_count=correct_count+?,incorrect_count=incorrect_count+?,successes=successes+?,lapses=lapses+?,last_reviewed_at=?,updated_at=? WHERE id=?", (int(correct), int(not correct), int(correct), int(not correct), timestamp, timestamp, card_id))
    connection.execute("INSERT INTO reviews(card_id,session_id,mode,rating,response,reviewed_at,correct) VALUES(?,?,?,?,?,?,?)", (card_id, session_id, mode, "good" if correct else "again", response, timestamp, int(correct)))


def _activity(connection, kind, detail, deck_id):
    connection.execute("INSERT INTO activity(kind,detail,deck_id,happened_at) VALUES(?,?,?,?)", (kind, detail, deck_id, utcnow()))


def _normalize_positions(connection, deck_id):
    for position, row in enumerate(connection.execute("SELECT id FROM cards WHERE deck_id=? ORDER BY position,id", (deck_id,))):
        connection.execute("UPDATE cards SET position=? WHERE id=?", (position, row["id"]))


def _streak(date_strings):
    dates = {datetime.date.fromisoformat(value) for value in date_strings if value}
    today = datetime.datetime.now().astimezone().date()
    cursor = today if today in dates else today - datetime.timedelta(days=1)
    streak = 0
    while cursor in dates:
        streak += 1
        cursor -= datetime.timedelta(days=1)
    return streak
