"""FastAPI application and typed local REST API."""
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, File, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, service
from .db import DB, EXPORTS, MEDIA, conn

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Study Sprout", version=__version__, docs_url="/api/docs", redoc_url=None)


class DeckInput(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    term_language: str = "auto"
    definition_language: str = "auto"
    draft: bool = False


class DeckUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)
    term_language: Optional[str] = None
    definition_language: Optional[str] = None
    draft: Optional[bool] = None


class CardInput(BaseModel):
    deck_id: int
    front: str = Field(min_length=1, max_length=5000)
    back: str = Field(min_length=1, max_length=5000)
    hint: str = Field(default="", max_length=2000)
    tags: str = Field(default="", max_length=500)
    english: str = Field(default="", max_length=5000)
    spanish: str = Field(default="", max_length=5000)
    kind: str = "written"
    options: List[str] = []
    explanation: str = Field(default="", max_length=5000)
    alternate_answers: List[str] = []
    term_language: str = "auto"
    definition_language: str = "auto"
    image_path: str = ""
    starred: bool = False


class BulkCards(BaseModel):
    deck_id: int
    cards: List[Dict[str, Any]]


class CardUpdate(BaseModel):
    front: Optional[str] = None
    back: Optional[str] = None
    hint: Optional[str] = None
    tags: Optional[str] = None
    english: Optional[str] = None
    spanish: Optional[str] = None
    kind: Optional[str] = None
    options: Optional[List[str]] = None
    explanation: Optional[str] = None
    alternate_answers: Optional[List[str]] = None
    term_language: Optional[str] = None
    definition_language: Optional[str] = None
    image_path: Optional[str] = None
    starred: Optional[bool] = None
    position: Optional[int] = None


class ReviewInput(BaseModel):
    card_id: int
    rating: str
    session_id: Optional[int] = None


class FolderInput(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)


class FolderUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class FolderDeckInput(BaseModel):
    deck_id: int
    included: bool = True


class CombineInput(BaseModel):
    deck_ids: List[int]
    title: Optional[str] = None
    persist: bool = True


class SessionInput(BaseModel):
    deck_id: int
    mode: str = "learn"
    options: Dict[str, Any] = {}


class SessionAnswer(BaseModel):
    response: str = ""
    card_id: Optional[int] = None
    override: bool = False
    elapsed_ms: int = 0


class QuizInput(BaseModel):
    deck_id: int
    limit: int = Field(default=10, ge=1, le=100)
    types: List[str] = ["multiple_choice", "true_false", "written"]
    starred_only: bool = False


class QuizSubmit(BaseModel):
    answers: Dict[str, str]
    grading: str = "strict"


class MatchInput(BaseModel):
    deck_id: int
    elapsed_ms: int = Field(gt=0)
    mistakes: int = Field(default=0, ge=0)


class ImportInput(BaseModel):
    payload: str
    format: str = "json"
    title: Optional[str] = None
    term_separator: Optional[str] = None
    row_separator: Optional[str] = None


@app.get("/api/health")
def health():
    try:
        conn().execute("SELECT 1").fetchone()
        database = "ok"
    except Exception:
        database = "error"
    return {"status": "ok" if database == "ok" else "degraded", "version": __version__, "database": database, "database_path": str(DB), "frontend": "ok" if (STATIC / "index.html").exists() else "missing", "local_time": service.utcnow() if hasattr(service, "utcnow") else "", "pid": os.getpid(), "instance_token": os.getenv("STUDY_INSTANCE_TOKEN", "")}


@app.get("/api/decks")
def decks(q: str = "", folder_id: Optional[int] = None): return service.list_decks(q, folder_id)
@app.post("/api/decks")
def create_deck(value: DeckInput): return service.create_deck(**value.model_dump())
@app.get("/api/decks/{deck_id}")
def get_deck(deck_id: int): return service.get_deck(deck_id)
@app.patch("/api/decks/{deck_id}")
def update_deck(deck_id: int, value: DeckUpdate): return service.update_deck(deck_id, **value.model_dump())
@app.delete("/api/decks/{deck_id}")
def delete_deck(deck_id: int): return service.delete_deck(deck_id)
@app.post("/api/decks/{deck_id}/duplicate")
def duplicate_deck(deck_id: int, title: Optional[str] = Body(default=None, embed=True)): return service.duplicate_deck(deck_id, title)
@app.post("/api/decks/combine")
def combine_decks(value: CombineInput): return service.combine_decks(value.deck_ids, value.title, value.persist)


@app.get("/api/decks/{deck_id}/cards")
def cards(deck_id: int, q: str = "", starred: Optional[bool] = None, mastery: Optional[str] = None): return service.list_cards(deck_id, q, starred, mastery)
@app.post("/api/cards")
def create_card(value: CardInput): return service.create_card(**value.model_dump())
@app.post("/api/cards/bulk")
def create_cards(value: BulkCards): return service.create_flashcards_bulk(value.deck_id, value.cards)
@app.get("/api/cards/{card_id}")
def get_card(card_id: int): return service.get_card(card_id)
@app.patch("/api/cards/{card_id}")
def update_card(card_id: int, value: CardUpdate): return service.update_card(card_id, **value.model_dump())
@app.delete("/api/cards/{card_id}")
def delete_card(card_id: int): return service.delete_card(card_id)
@app.post("/api/cards/{card_id}/star")
def star_card(card_id: int, starred: Optional[bool] = Body(default=None, embed=True)): return service.toggle_star(card_id, starred)
@app.post("/api/decks/{deck_id}/reorder")
def reorder(deck_id: int, card_ids: List[int] = Body(embed=True)): return service.reorder_cards(deck_id, card_ids)
@app.get("/api/search")
def search(q: str = Query(min_length=1), deck_id: Optional[int] = None): return service.search_cards(q, deck_id)


@app.get("/api/folders")
def folders(): return service.list_folders()
@app.post("/api/folders")
def create_folder(value: FolderInput): return service.create_folder(value.title, value.description)
@app.patch("/api/folders/{folder_id}")
def update_folder(folder_id: int, value: FolderUpdate): return service.update_folder(folder_id, value.title, value.description)
@app.delete("/api/folders/{folder_id}")
def delete_folder(folder_id: int): return service.delete_folder(folder_id)
@app.post("/api/folders/{folder_id}/decks")
def set_folder_deck(folder_id: int, value: FolderDeckInput): return service.set_folder_deck(folder_id, value.deck_id, value.included)


@app.post("/api/sessions")
def start_session(value: SessionInput): return service.start_session(value.deck_id, value.mode, value.options)
@app.get("/api/sessions/{session_id}")
def get_session(session_id: int): return service.get_session(session_id)
@app.post("/api/sessions/{session_id}/answer")
def answer_session(session_id: int, value: SessionAnswer): return service.answer_session(session_id, value.response, value.card_id, value.override, value.elapsed_ms)
@app.post("/api/sessions/{session_id}/override-last")
def override_last(session_id: int): return service.override_last_answer(session_id)
@app.post("/api/reviews")
def record_review(value: ReviewInput): return service.record_review(value.card_id, value.rating, value.session_id)
@app.get("/api/due")
def due(deck_id: Optional[int] = None, limit: int = 100): return service.get_due_cards(deck_id, limit)


@app.post("/api/tests")
def create_test(value: QuizInput): return service.generate_quiz(value.deck_id, value.limit, value.types, value.starred_only)
@app.post("/api/tests/{session_id}/submit")
def submit_test(session_id: int, value: QuizSubmit): return service.submit_quiz(session_id, value.answers, value.grading)
@app.get("/api/tests/{session_id}/results")
def test_results(session_id: int): return service.get_quiz_results(session_id)
@app.post("/api/match/scores")
def match_score(value: MatchInput): return service.record_match_score(value.deck_id, value.elapsed_ms, value.mistakes)
@app.get("/api/decks/{deck_id}/match-scores")
def match_scores(deck_id: int): return service.get_match_scores(deck_id)
@app.get("/api/progress")
def progress(deck_id: Optional[int] = None): return service.get_progress(deck_id)
@app.get("/api/activity")
def activity(limit: int = 20): return service.get_recent_activity(limit)


@app.post("/api/import/preview")
def import_preview(value: ImportInput): return service.preview_import(value.payload, value.format, value.term_separator, value.row_separator)
@app.post("/api/import")
def import_commit(value: ImportInput): return service.import_deck(value.payload, value.format, value.title, value.term_separator, value.row_separator)
@app.get("/api/decks/{deck_id}/export")
def export(deck_id: int, format: str = "json"): return service.export_deck(deck_id, format)
@app.post("/api/media")
async def upload_media(file: UploadFile = File(...)):
    data = await file.read(5 * 1024 * 1024 + 1)
    return service.save_media(file.filename or "image", file.content_type or "", data)
@app.get("/api/media/{filename}")
def media(filename: str):
    path = MEDIA / Path(filename).name
    if path.is_file() and path.parent == MEDIA:
        return FileResponse(str(path))
    return {"success": False, "error": {"code": "not_found", "message": "Image not found"}}
@app.get("/api/exports/{filename}")
def download_export(filename: str):
    path = EXPORTS / Path(filename).name
    return FileResponse(str(path), filename=path.name) if path.is_file() and path.parent == EXPORTS else {"success": False, "error": {"code": "not_found", "message": "Export not found"}}


app.mount("/assets", StaticFiles(directory=str(STATIC)), name="assets")


@app.get("/")
def index(): return FileResponse(str(STATIC / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("STUDY_PORT", "8080")), access_log=False)
