import os, sqlite3, json, datetime
from pathlib import Path

DATA = Path(os.environ.get('STUDY_DATA_DIR', Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'local-study-app'))
DB = DATA / 'study.db'

def conn():
    DATA.mkdir(parents=True, exist_ok=True)
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init_db():
    with conn() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS decks(id INTEGER PRIMARY KEY, title TEXT UNIQUE NOT NULL, description TEXT DEFAULT '', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS cards(id INTEGER PRIMARY KEY, deck_id INTEGER NOT NULL, front TEXT NOT NULL, back TEXT NOT NULL, hint TEXT DEFAULT '', tags TEXT DEFAULT '', english TEXT DEFAULT '', spanish TEXT DEFAULT '', kind TEXT DEFAULT 'written', options TEXT DEFAULT '[]', explanation TEXT DEFAULT '', due_at TEXT, ease REAL DEFAULT 2.5, interval INTEGER DEFAULT 0, successes INTEGER DEFAULT 0, lapses INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY, card_id INTEGER, rating TEXT, reviewed_at TEXT, correct INTEGER);
        CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY, kind TEXT, detail TEXT, happened_at TEXT);''')
        seed(c)

def seed(c):
    if c.execute('select count(*) from decks').fetchone()[0]: return
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    for title,desc in [('Spanish MTEL Practice','Core Spanish vocabulary and classroom practice.'),('Biology Basics','A quick tour of living systems.')]:
        did=c.execute('insert into decks(title,description,created_at) values(?,?,?)',(title,desc,now)).lastrowid
        items=[('¿Cómo estás?','How are you?','', 'greetings','How are you?','¿Cómo estás?','written','[]','A common greeting.'),('¿Qué significa casa?','House','', 'vocabulary','House','Casa','mc','["House","Car","Book"]','Casa means house.'),('El sol es una estrella.','True','', 'science','The sun is a star.','El sol es una estrella.','truefalse','["True","False"]','The Sun is a star.'),('Buenos días','Good morning','', 'greetings','Good morning','Buenos días','written','[]','Used in the morning.'),('¿Dónde está la biblioteca?','Where is the library?','','travel','Where is the library?','¿Dónde está la biblioteca?','written','[]','A useful question.'),('Gracias','Thank you','','greetings','Thank you','Gracias','written','[]','A polite expression.'),('Rojo','Red','','colors','Red','Rojo','written','[]','A color.'),('Uno, dos, tres','One, two, three','','numbers','One, two, three','Uno, dos, tres','written','[]','Counting.'),('¿Qué hora es?','What time is it?','','questions','What time is it?','¿Qué hora es?','written','[]','Ask the time.'),('Amigo','Friend','','people','Friend','Amigo','written','[]','A person you know.'),('La biblioteca está cerca.','The library is nearby.','','travel','The library is nearby.','La biblioteca está cerca.','written','[]','Location phrase.'),('¿Cuál es tu nombre?','What is your name?','','questions','What is your name?','¿Cuál es tu nombre?','written','[]','Ask a name.')]
        if title=='Biology Basics': items=[('What is a cell?','The basic unit of life','','cells','','','written','[]','Cells are life’s basic units.'),('Plants make food by photosynthesis.','True','','plants','','','truefalse','["True","False"]','Photosynthesis makes sugars.'),('DNA carries genetic information.','True','','genetics','','','truefalse','["True","False"]','DNA stores instructions.')]
        for it in items: c.execute('insert into cards(deck_id,front,back,hint,tags,english,spanish,kind,options,explanation,due_at) values(?,?,?,?,?,?,?,?,?,?,?)',(did,*it,now))

init_db()
