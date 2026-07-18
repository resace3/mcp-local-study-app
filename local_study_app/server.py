import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from . import service
from .db import conn

app = FastAPI(title='Local Study App', version='1.0.0')
class DeckIn(BaseModel): title: str; description: str = ''
class CardIn(BaseModel):
    deck_id: int; front: str; back: str; hint: str = ''; tags: str = ''; english: str = ''; spanish: str = ''; kind: str = 'written'; options: list = []; explanation: str = ''
class ReviewIn(BaseModel): card_id: int; rating: str

@app.get('/api/health')
def health():
    try: conn().execute('select 1'); db='ok'
    except Exception: db='error'
    return {'status':'ok','version':'1.0.0','database':db,'frontend':'ok'}
@app.get('/api/decks')
def decks(): return service.list_decks()
@app.post('/api/decks')
def create_deck(x: DeckIn): return service.create_deck(x.title, x.description)
@app.get('/api/decks/{did}/cards')
def cards(did: int, q: str = ''): return service.list_cards(did, q)
@app.post('/api/cards')
def create_card(x: CardIn): return service.create_card(**x.model_dump())
@app.post('/api/reviews')
def reviews(x: ReviewIn): return service.review(x.card_id, x.rating)
@app.get('/api/progress')
def progress(): return service.progress()
@app.get('/api/due')
def due(): return service.due()
@app.get('/', response_class=HTMLResponse)
def home(): return HTML

HTML = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Study Sprout</title><style>
:root{--ink:#24334b;--blue:#5b7cfa;--mint:#a8e6cf;--cream:#fffaf2}*{box-sizing:border-box}body{margin:0;background:var(--cream);color:var(--ink);font:16px system-ui,sans-serif}header{background:#fff;padding:20px 5%;display:flex;justify-content:space-between;align-items:center;box-shadow:0 2px 10px #24334b12}h1{margin:0;color:var(--blue)}main{max-width:1100px;margin:28px auto;padding:0 20px}.hero{background:linear-gradient(135deg,#e6edff,#fff);border-radius:24px;padding:28px;display:flex;justify-content:space-between;gap:20px}.stats,.decks{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin:20px 0}.stat,.deck{background:white;border-radius:18px;padding:20px;box-shadow:0 5px 18px #24334b12}.stat b{display:block;font-size:32px;color:var(--blue)}button{border:0;border-radius:12px;padding:12px 18px;background:var(--blue);color:white;font-weight:700;cursor:pointer;margin:4px}.secondary{background:#e8edff;color:var(--blue)}.pill{display:inline-block;background:var(--mint);padding:5px 10px;border-radius:99px;font-size:12px}@media(max-width:500px){.hero{display:block}.hero button{width:100%;margin-top:12px}}
</style></head><body><header><h1>🌱 Study Sprout</h1><span>Local • private • yours</span></header><main><section class="hero"><div><h2>Grow your knowledge, one card at a time.</h2><p>Friendly flashcards, quizzes, and progress tracking that stay on this computer.</p></div><button onclick="newDeck()">＋ New deck</button></section><section class="stats"><div class="stat"><b id="decks">0</b>Decks</div><div class="stat"><b id="cards">0</b>Total cards</div><div class="stat"><b id="due">0</b>Due today</div><div class="stat"><b id="mastered">0</b>Mastered</div></section><h2>Your decks</h2><div id="list" class="decks"></div><section class="stat"><h2>Quick study</h2><p id="message">Choose a deck to see its cards.</p><div id="cardsView"></div></section></main><script>
async function api(u,o){let r=await fetch(u,o);return r.json()}async function load(){let d=await api('/api/decks'),p=await api('/api/progress');document.querySelector('#decks').textContent=d.data.length;document.querySelector('#cards').textContent=p.data.total_cards;document.querySelector('#due').textContent=p.data.due;document.querySelector('#mastered').textContent=p.data.mastered;document.querySelector('#list').innerHTML=d.data.map(x=>`<article class="deck"><span class="pill">${x.card_count} cards</span><h3>${esc(x.title)}</h3><p>${esc(x.description||'Ready to study')}</p><button onclick="show(${x.id},'${esc(x.title)}')">Study deck</button></article>`).join('')}function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}async function show(id,title){let r=await api('/api/decks/'+id+'/cards');document.querySelector('#message').textContent=title+' • '+r.data.length+' cards';document.querySelector('#cardsView').innerHTML=r.data.slice(0,5).map(x=>`<p><b>${esc(x.front)}</b> — ${esc(x.back)} <button class="secondary" onclick="review(${x.id})">Good</button></p>`).join('')}async function review(id){await api('/api/reviews',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({card_id:id,rating:'good'})});load()}async function newDeck(){let t=prompt('Deck title');if(t){let r=await api('/api/decks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:t})});if(!r.success)alert(r.error.message);load()}}load();</script></body></html>'''

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=int(os.getenv('STUDY_PORT','8080')))
