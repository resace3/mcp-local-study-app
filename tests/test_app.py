import json
import os
import tempfile
import uuid

os.environ["STUDY_DATA_DIR"] = tempfile.mkdtemp(prefix="study-sprout-tests-")

from fastapi.testclient import TestClient

from local_study_app import mcp_server, service
from local_study_app.db import DB, conn, init_db
from local_study_app.server import app

client = TestClient(app)


def new_deck(prefix="Test Deck"):
    result = service.create_deck("%s %s" % (prefix, uuid.uuid4().hex[:8]), "A test deck")
    assert result["success"]
    return result["data"]["id"]


def add_cards(deck_id, count=6):
    cards = [{"front": "Question %d" % index, "back": "Answer %d" % index, "hint": "Hint %d" % index, "tags": "topic"} for index in range(count)]
    result = service.create_flashcards_bulk(deck_id, cards)
    assert result["success"]
    return result["data"]["ids"]


def test_database_initialization_and_seed_data():
    init_db()
    assert DB.exists()
    decks = service.list_decks()["data"]
    assert {item["title"] for item in decks} >= {"Spanish MTEL Practice", "Biology Basics"}
    spanish = next(item for item in decks if item["title"] == "Spanish MTEL Practice")
    assert spanish["card_count"] >= 12
    assert service.list_cards(spanish["id"])["data"][0]["front"].startswith("¿")


def test_deck_crud_duplicate_and_combine():
    first = new_deck("Deck CRUD")
    second = new_deck("Deck Combine")
    add_cards(first, 3)
    add_cards(second, 2)
    assert service.update_deck(first, title="Renamed %s" % uuid.uuid4().hex[:6], description="Changed")["success"]
    duplicate = service.duplicate_deck(first)
    assert duplicate["success"] and duplicate["data"]["card_count"] == 3
    combined = service.combine_decks([first, second], "Combined %s" % uuid.uuid4().hex[:6], True)
    assert combined["success"]
    assert len(service.list_cards(combined["data"]["id"])["data"]) == 5
    assert service.delete_deck(second)["success"]
    assert not service.get_deck(second)["success"]


def test_card_crud_search_bulk_reorder_and_stars():
    deck_id = new_deck("Cards")
    ids = add_cards(deck_id, 5)
    assert service.get_card(ids[0])["success"]
    assert service.update_card(ids[0], front="Updated question", alternate_answers=["Alt"], starred=True)["success"]
    assert service.search_cards("Updated", deck_id)["data"][0]["id"] == ids[0]
    assert service.toggle_star(ids[0], False)["data"]["starred"] is False
    reversed_ids = list(reversed(ids))
    assert service.reorder_cards(deck_id, reversed_ids)["success"]
    assert service.list_cards(deck_id)["data"][0]["id"] == ids[-1]
    assert service.delete_card(ids[1])["success"]
    assert not service.get_card(ids[1])["success"]


def test_multiple_choice_validation():
    deck_id = new_deck("Validation")
    invalid = service.create_card(deck_id, "Question", "Answer", kind="multiple_choice", options=["Answer", "Other"])
    assert not invalid["success"]
    valid = service.create_card(deck_id, "Question", "Answer", kind="multiple_choice", options=["Answer", "Other", "Third"])
    assert valid["success"]


def test_folders_and_membership():
    deck_id = new_deck("Folder deck")
    folder = service.create_folder("Folder %s" % uuid.uuid4().hex[:8], "Grouped material")
    assert folder["success"]
    folder_id = folder["data"]["id"]
    assert service.set_folder_deck(folder_id, deck_id, True)["success"]
    assert service.get_deck(deck_id)["data"]["folder_ids"] == [folder_id]
    assert service.list_decks(folder_id=folder_id)["data"][0]["id"] == deck_id
    assert service.set_folder_deck(folder_id, deck_id, False)["success"]
    assert service.delete_folder(folder_id)["success"]


def test_transparent_grading_levels():
    assert service.grade_answer("Hello!", "hello", level="strict")
    assert service.grade_answer("como", "cómo", level="moderate")
    assert service.grade_answer("cell basic unit", "basic unit cell", level="relaxed")
    assert service.grade_answer("mitochondria", "mitochondrion", level="moderate")
    assert not service.grade_answer("wrong", "right", level="relaxed")


def test_learn_write_spell_sessions_and_override():
    deck_id = new_deck("Sessions")
    ids = add_cards(deck_id, 2)
    for mode in ("learn", "write", "spell"):
        started = service.start_session(deck_id, mode, {"shuffle": False, "grading": "strict"})
        assert started["success"] and started["data"]["mode"] == mode
        session = started["data"]
        card = session["current_card"]
        wrong = service.answer_session(session["id"], "wrong", card["id"])
        assert wrong["success"] and not wrong["data"]["correct"]
        assert wrong["data"]["prompt"]
        override = service.override_last_answer(session["id"])
        assert override["success"]
        assert override["data"]["session"]["correct"] == 1
        assert override["data"]["session"]["incorrect"] == 0
        current = service.get_session(session["id"])["data"]
        if current["status"] == "active":
            next_card = current["current_card"]
            correct = service.answer_session(session["id"], next_card["back"], next_card["id"])
            assert correct["data"]["correct"]
    assert service.get_card(ids[0])["data"]["correct_count"] >= 1


def test_learn_goal_and_adaptive_ordering():
    deck_id = new_deck("Adaptive")
    ids = add_cards(deck_id, 2)
    service.record_review(ids[1], "again")
    started = service.start_session(deck_id, "learn", {"shuffle": False, "adaptive": True, "target_repetitions": 1})
    assert started["data"]["current_card"]["id"] == ids[1]
    card = started["data"]["current_card"]
    answered = service.answer_session(started["data"]["id"], card["back"], card["id"])
    assert answered["data"]["session"]["queue"].count(card["id"]) == 1


def test_quiz_generation_submission_and_results():
    deck_id = new_deck("Quiz")
    add_cards(deck_id, 6)
    generated = service.generate_quiz(deck_id, 6, ["multiple_choice", "written"])
    assert generated["success"] and len(generated["data"]["questions"]) == 6
    assert {question["type"] for question in generated["data"]["questions"]} == {"multiple_choice", "written"}
    true_false = service.generate_quiz(deck_id, 3, ["true_false"])
    assert true_false["success"]
    assert all(question["type"] == "true_false" and question["options"] == ["True", "False"] for question in true_false["data"]["questions"])
    assert not service.generate_quiz(deck_id, 3, [])["success"]
    session_id = generated["data"]["session_id"]
    with conn() as connection:
        raw = json.loads(connection.execute("SELECT state FROM study_sessions WHERE id=?", (session_id,)).fetchone()[0])
    answers = {str(item["card_id"]): item["answer"] for item in raw["questions"]}
    submitted = service.submit_quiz(session_id, answers)
    assert submitted["success"] and submitted["data"]["score"] == 100
    assert service.get_quiz_results(session_id)["data"]["complete"]


def test_spaced_repetition_progress_activity_and_match():
    deck_id = new_deck("Progress")
    card_id = add_cards(deck_id, 1)[0]
    assert service.record_review(card_id, "easy")["data"]["interval"] >= 7
    progress = service.get_progress(deck_id)["data"]
    assert progress["mastered"] == 1 and progress["accuracy"] == 100
    assert {"study_time_ms", "most_missed", "quiz_scores", "mode_completion"} <= set(progress)
    before = progress["mastered"]
    score = service.record_match_score(deck_id, 12000, 1)
    assert score["success"] and score["data"]["new_best"]
    assert service.get_match_scores(deck_id)["data"]["best_ms"] == 12000
    assert service.get_progress(deck_id)["data"]["mastered"] == before
    assert service.get_recent_activity()["data"]


def test_json_csv_text_import_export_and_invalid_preview():
    payload = json.dumps({"title": "Imported %s" % uuid.uuid4().hex[:6], "cards": [{"front": "A", "back": "B"}, {"front": "C", "back": "D"}]})
    imported = service.import_deck(payload, "json")
    assert imported["success"]
    deck_id = imported["data"]["deck_id"]
    for fmt in ("json", "csv", "text"):
        exported = service.export_deck(deck_id, fmt)
        assert exported["success"] and exported["data"]["content"]
    csv_payload = "front,back\nOne,Uno\nTwo,Dos\n"
    assert service.preview_import(csv_payload, "csv")["data"]["card_count"] == 2
    assert service.preview_import("One\tUno\nTwo\tDos", "text")["data"]["card_count"] == 2
    assert not service.preview_import('{"cards":[{"front":"missing back"}]}', "json")["success"]


def test_image_validation():
    assert service.save_media("not.png", "text/plain", b"hello")["success"] is False
    assert service.save_media("fake.png", "image/png", b"not really a png")["success"] is False
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    assert service.save_media("small.png", "image/png", png)["success"]


def test_rest_api_health_and_major_resources():
    assert client.get("/api/health").json()["status"] == "ok"
    created = client.post("/api/decks", json={"title": "API %s" % uuid.uuid4().hex[:8]}).json()
    assert created["success"]
    deck_id = created["data"]["id"]
    card = client.post("/api/cards", json={"deck_id": deck_id, "front": "Term", "back": "Definition"}).json()
    assert card["success"]
    assert client.get("/api/decks/%d/cards" % deck_id).json()["data"][0]["front"] == "Term"
    assert client.get("/").status_code == 200
    assert client.get("/assets/app.js").status_code == 200


def test_mcp_tool_schemas_success_and_errors():
    listing = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tools = listing["result"]["tools"]
    assert len(tools) >= 35
    assert all(item["description"] and item["inputSchema"]["type"] == "object" for item in tools)
    success = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_decks", "arguments": {}}})
    assert success["result"]["structuredContent"]["success"]
    failure = mcp_server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_deck", "arguments": {}}})
    assert failure["result"]["isError"]
    unknown = mcp_server.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "no_such_tool", "arguments": {}}})
    assert "error" in unknown
