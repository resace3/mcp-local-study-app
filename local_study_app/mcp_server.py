"""Dependency-free MCP stdio server with explicit tool schemas."""
import json
import sys
import webbrowser

from . import __version__, process, service


def schema(properties=None, required=None):
    return {"type": "object", "properties": properties or {}, "required": required or [], "additionalProperties": False}


INTEGER = {"type": "integer"}
STRING = {"type": "string"}
BOOLEAN = {"type": "boolean"}


def tool(description, input_schema, handler):
    return {"description": description, "inputSchema": input_schema, "handler": handler}


TOOLS = {
    "start_study_app": tool("Start the localhost study website idempotently and wait for its health check.", schema(), lambda a: process.start()),
    "open_study_app": tool("Start the app if needed and open its local URL in the default browser.", schema(), lambda a: _open()),
    "get_study_app_status": tool("Return web process, URL, port, PID, health, and database status.", schema(), lambda a: process.status()),
    "stop_study_app": tool("Stop only the web process previously started by this project.", schema(), lambda a: process.stop()),
    "list_decks": tool("List local decks with card and mastery counts.", schema({"query": STRING, "folder_id": INTEGER}), lambda a: service.list_decks(a.get("query", ""), a.get("folder_id"))),
    "get_deck": tool("Get one deck by numeric id.", schema({"deck_id": INTEGER}, ["deck_id"]), lambda a: service.get_deck(a["deck_id"])),
    "create_deck": tool("Create a uniquely named local deck.", schema({"title": STRING, "description": STRING, "term_language": STRING, "definition_language": STRING}, ["title"]), lambda a: service.create_deck(a["title"], a.get("description", ""), a.get("term_language", "auto"), a.get("definition_language", "auto"))),
    "update_deck": tool("Rename a deck or update its description and languages.", schema({"deck_id": INTEGER, "title": STRING, "description": STRING, "term_language": STRING, "definition_language": STRING}, ["deck_id"]), lambda a: service.update_deck(a.pop("deck_id"), **a)),
    "delete_deck": tool("Permanently delete a deck and its cards.", schema({"deck_id": INTEGER}, ["deck_id"]), lambda a: service.delete_deck(a["deck_id"])),
    "duplicate_deck": tool("Copy a deck and every card into a new deck.", schema({"deck_id": INTEGER, "title": STRING}, ["deck_id"]), lambda a: service.duplicate_deck(a["deck_id"], a.get("title"))),
    "combine_decks": tool("Create a permanent combined deck or return a temporary combined card set.", schema({"deck_ids": {"type": "array", "items": INTEGER, "minItems": 2}, "title": STRING, "persist": BOOLEAN}, ["deck_ids"]), lambda a: service.combine_decks(a["deck_ids"], a.get("title"), a.get("persist", True))),
    "list_cards": tool("List cards in a deck with optional search, star, and mastery filters.", schema({"deck_id": INTEGER, "query": STRING, "starred": BOOLEAN, "mastery": {"type": "string", "enum": ["not_studied", "still_learning", "mastered"]}}, ["deck_id"]), lambda a: service.list_cards(a["deck_id"], a.get("query", ""), a.get("starred"), a.get("mastery"))),
    "get_card": tool("Get one flashcard by id.", schema({"card_id": INTEGER}, ["card_id"]), lambda a: service.get_card(a["card_id"])),
    "create_flashcard": tool("Add one typed flashcard to a deck.", schema({"deck_id": INTEGER, "front": STRING, "back": STRING, "hint": STRING, "tags": STRING, "kind": {"type": "string", "enum": ["written", "multiple_choice", "true_false"]}, "options": {"type": "array", "items": STRING}, "explanation": STRING, "alternate_answers": {"type": "array", "items": STRING}, "starred": BOOLEAN}, ["deck_id", "front", "back"]), lambda a: service.create_card(**a)),
    "create_flashcards_bulk": tool("Validate and create several cards in one deck.", schema({"deck_id": INTEGER, "cards": {"type": "array", "items": {"type": "object"}, "minItems": 1}}, ["deck_id", "cards"]), lambda a: service.create_flashcards_bulk(a["deck_id"], a["cards"])),
    "update_flashcard": tool("Edit a card's content, type, options, explanation, alternates, tags, or star.", schema({"card_id": INTEGER, "front": STRING, "back": STRING, "hint": STRING, "tags": STRING, "kind": STRING, "options": {"type": "array", "items": STRING}, "explanation": STRING, "alternate_answers": {"type": "array", "items": STRING}, "starred": BOOLEAN}, ["card_id"]), lambda a: service.update_card(a.pop("card_id"), **a)),
    "delete_flashcard": tool("Delete one flashcard.", schema({"card_id": INTEGER}, ["card_id"]), lambda a: service.delete_card(a["card_id"])),
    "search_flashcards": tool("Search terms, definitions, hints, and tags across one or all decks.", schema({"query": STRING, "deck_id": INTEGER}, ["query"]), lambda a: service.search_cards(a["query"], a.get("deck_id"))),
    "set_flashcard_star": tool("Star or unstar a card for focused study.", schema({"card_id": INTEGER, "starred": BOOLEAN}, ["card_id", "starred"]), lambda a: service.toggle_star(a["card_id"], a["starred"])),
    "reorder_flashcards": tool("Persist an exact card order for a deck.", schema({"deck_id": INTEGER, "card_ids": {"type": "array", "items": INTEGER}}, ["deck_id", "card_ids"]), lambda a: service.reorder_cards(a["deck_id"], a["card_ids"])),
    "start_study_session": tool("Start a resumable Flashcards, Learn, Write, Spell, or Test session.", schema({"deck_id": INTEGER, "mode": {"type": "string", "enum": ["flashcards", "learn", "write", "spell", "test"]}, "options": {"type": "object"}}, ["deck_id", "mode"]), lambda a: service.start_session(a["deck_id"], a["mode"], a.get("options", {}))),
    "get_study_session": tool("Resume or inspect a study session.", schema({"session_id": INTEGER}, ["session_id"]), lambda a: service.get_session(a["session_id"])),
    "submit_study_answer": tool("Submit an answer to the current Learn, Write, or Spell item.", schema({"session_id": INTEGER, "response": STRING, "card_id": INTEGER, "override": BOOLEAN, "elapsed_ms": INTEGER}, ["session_id"]), lambda a: service.answer_session(a["session_id"], a.get("response", ""), a.get("card_id"), a.get("override", False), a.get("elapsed_ms", 0))),
    "override_study_answer": tool("Mark the most recent rejected written answer correct and update progress.", schema({"session_id": INTEGER}, ["session_id"]), lambda a: service.override_last_answer(a["session_id"])),
    "generate_quiz_from_deck": tool("Generate a local Test session from existing cards without an external model.", schema({"deck_id": INTEGER, "limit": INTEGER, "types": {"type": "array", "items": {"type": "string", "enum": ["multiple_choice", "true_false", "written"]}}, "starred_only": BOOLEAN}, ["deck_id"]), lambda a: service.generate_quiz(a["deck_id"], a.get("limit", 10), a.get("types"), a.get("starred_only", False))),
    "submit_quiz_answer": tool("Submit all answers for a generated test and calculate its score.", schema({"session_id": INTEGER, "answers": {"type": "object", "additionalProperties": STRING}, "grading": {"type": "string", "enum": ["strict", "moderate", "relaxed"]}}, ["session_id", "answers"]), lambda a: service.submit_quiz(a["session_id"], a["answers"], a.get("grading", "strict"))),
    "get_quiz_results": tool("Retrieve score and answer review for a test.", schema({"session_id": INTEGER}, ["session_id"]), lambda a: service.get_quiz_results(a["session_id"])),
    "get_due_cards": tool("Return spaced-repetition cards due now.", schema({"deck_id": INTEGER, "limit": INTEGER}), lambda a: service.get_due_cards(a.get("deck_id"), a.get("limit", 100))),
    "record_card_review": tool("Rate a flashcard Again, Hard, Good, or Easy and update its due date.", schema({"card_id": INTEGER, "rating": {"type": "string", "enum": ["again", "hard", "good", "easy"]}, "session_id": INTEGER}, ["card_id", "rating"]), lambda a: service.record_review(a["card_id"], a["rating"], a.get("session_id"))),
    "get_study_progress": tool("Get mastery groups, due count, accuracy, streak, sessions, and Match history.", schema({"deck_id": INTEGER}), lambda a: service.get_progress(a.get("deck_id"))),
    "get_recent_activity": tool("Get recent deck, study, review, Test, and Match activity.", schema({"limit": INTEGER}), lambda a: service.get_recent_activity(a.get("limit", 20))),
    "record_match_score": tool("Record a completed local Match game without changing mastery.", schema({"deck_id": INTEGER, "elapsed_ms": INTEGER, "mistakes": INTEGER}, ["deck_id", "elapsed_ms"]), lambda a: service.record_match_score(a["deck_id"], a["elapsed_ms"], a.get("mistakes", 0))),
    "get_match_scores": tool("Get personal Match best and recent scores for a deck.", schema({"deck_id": INTEGER}, ["deck_id"]), lambda a: service.get_match_scores(a["deck_id"])),
    "list_folders": tool("List local study folders.", schema(), lambda a: service.list_folders()),
    "create_folder": tool("Create a local folder for decks.", schema({"title": STRING, "description": STRING}, ["title"]), lambda a: service.create_folder(a["title"], a.get("description", ""))),
    "update_folder": tool("Rename or describe a local folder.", schema({"folder_id": INTEGER, "title": STRING, "description": STRING}, ["folder_id"]), lambda a: service.update_folder(a["folder_id"], a.get("title"), a.get("description"))),
    "delete_folder": tool("Delete a folder without deleting its decks.", schema({"folder_id": INTEGER}, ["folder_id"]), lambda a: service.delete_folder(a["folder_id"])),
    "set_folder_deck": tool("Add or remove a deck from a folder.", schema({"folder_id": INTEGER, "deck_id": INTEGER, "included": BOOLEAN}, ["folder_id", "deck_id"]), lambda a: service.set_folder_deck(a["folder_id"], a["deck_id"], a.get("included", True))),
    "preview_deck_import": tool("Validate JSON, CSV, or separated text and return a preview without writing data.", schema({"payload": STRING, "format": {"type": "string", "enum": ["json", "csv", "text"]}, "term_separator": STRING, "row_separator": STRING}, ["payload", "format"]), lambda a: service.preview_import(a["payload"], a["format"], a.get("term_separator"), a.get("row_separator"))),
    "import_deck": tool("Validate and import a complete JSON, CSV, or separated-text deck transactionally.", schema({"payload": STRING, "format": {"type": "string", "enum": ["json", "csv", "text"]}, "title": STRING, "term_separator": STRING, "row_separator": STRING}, ["payload", "format"]), lambda a: service.import_deck(a["payload"], a["format"], a.get("title"), a.get("term_separator"), a.get("row_separator"))),
    "export_deck": tool("Export one deck as project JSON, CSV, or tab-separated text.", schema({"deck_id": INTEGER, "format": {"type": "string", "enum": ["json", "csv", "text"]}}, ["deck_id"]), lambda a: service.export_deck(a["deck_id"], a.get("format", "json"))),
}


def _open():
    result = process.start()
    if result["success"]:
        webbrowser.open(result["data"]["url"])
        result["summary"] = "Study app opened"
    return result


def _tool_list():
    return [{"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]} for name, spec in TOOLS.items()]


def _validate_required(arguments, input_schema):
    missing = [name for name in input_schema.get("required", []) if name not in arguments]
    if missing:
        raise ValueError("Missing required argument(s): %s" % ", ".join(missing))


def _reply(request_id, result):
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(request):
    method = request.get("method")
    request_id = request.get("id")
    if method == "initialize":
        return _reply(request_id, {"protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "local-study-app", "version": __version__}, "instructions": "A private local study system. Start the app before browser work. Use deck/card tools to manage material, study-session tools for Learn/Write/Spell, quiz tools for tests, review tools for spaced repetition, and progress tools for results."})
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _reply(request_id, {})
    if method == "tools/list":
        return _reply(request_id, {"tools": _tool_list()})
    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        if name not in TOOLS:
            return _error(request_id, -32602, "Unknown tool: %s" % name)
        arguments = dict(params.get("arguments") or {})
        try:
            _validate_required(arguments, TOOLS[name]["inputSchema"])
            result = TOOLS[name]["handler"](arguments)
            return _reply(request_id, {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}], "structuredContent": result, "isError": not result.get("success", False)})
        except Exception as exc:
            result = service.err(str(exc), "tool_error")
            return _reply(request_id, {"content": [{"type": "text", "text": json.dumps(result)}], "structuredContent": result, "isError": True})
    return _error(request_id, -32601, "Method not found")


def main():
    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = handle(request)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except Exception as exc:
            sys.stdout.write(json.dumps(_error(None, -32700, "Parse error: %s" % exc)) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
