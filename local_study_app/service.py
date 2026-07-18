import json, csv, io, datetime, random, sqlite3
from .db import conn
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def ok(data=None,summary='Done'): return {'success':True,'data':data,'summary':summary,'error':None}
def err(message): return {'success':False,'data':None,'summary':'Request failed','error':{'message':message}}
def deck(d): return dict(d)
def card(c):
    x=dict(c); x['options']=json.loads(x.get('options') or '[]'); return x
def list_decks():
    with conn() as c: return ok([dict(x) | {'card_count':c.execute('select count(*) from cards where deck_id=?',(x['id'],)).fetchone()[0]} for x in c.execute('select * from decks order by id')])
def get_deck(did):
    with conn() as c:
        d=c.execute('select * from decks where id=?',(did,)).fetchone()
        return ok(deck(d)) if d else err('Deck not found')
def create_deck(title,description=''):
    if not title.strip(): return err('Title cannot be blank')
    try:
        with conn() as c: cur=c.execute('insert into decks(title,description,created_at) values(?,?,?)',(title.strip(),description,now())); return ok({'id':cur.lastrowid,'title':title.strip()},'Deck created')
    except sqlite3.IntegrityError: return err('A deck with that title already exists')
def update_deck(did,title=None,description=None):
    with conn() as c:
        if not c.execute('select 1 from decks where id=?',(did,)).fetchone(): return err('Deck not found')
        if title is not None and not title.strip(): return err('Title cannot be blank')
        c.execute('update decks set title=coalesce(?,title),description=coalesce(?,description) where id=?',(title.strip() if title else None,description,did)); return ok({'id':did},'Deck updated')
def delete_deck(did):
    with conn() as c: c.execute('delete from cards where deck_id=?',(did,)); n=c.execute('delete from decks where id=?',(did,)).rowcount; return ok({'deleted':n},'Deck deleted') if n else err('Deck not found')
def duplicate_deck(did,title=None):
    with conn() as c:
        d=c.execute('select * from decks where id=?',(did,)).fetchone()
        if not d:return err('Deck not found')
        title=title or d['title']+' Copy'; r=create_deck(title,d['description']);
        if not r['success']:return r
        for x in c.execute('select * from cards where deck_id=?',(did,)): create_card(r['data']['id'],**{k:x[k] for k in ['front','back','hint','tags','english','spanish','kind','options','explanation']})
        return r
def create_card(deck_id,front,back,hint='',tags='',english='',spanish='',kind='written',options=None,explanation=''):
    if not front.strip() or not back.strip(): return err('Front and back are required')
    with conn() as c:
        if not c.execute('select 1 from decks where id=?',(deck_id,)).fetchone(): return err('Deck not found')
        r=c.execute('insert into cards(deck_id,front,back,hint,tags,english,spanish,kind,options,explanation,due_at) values(?,?,?,?,?,?,?,?,?,?,?)',(deck_id,front,back,hint,tags,english,spanish,kind,json.dumps(options or []),explanation,now())); return ok({'id':r.lastrowid},'Card created')
def list_cards(deck_id,q=''):
    with conn() as c:
        rows=c.execute('select * from cards where deck_id=? and (front like ? or back like ? or tags like ?) order by id',(deck_id,f'%{q}%',f'%{q}%',f'%{q}%')).fetchall(); return ok([card(x) for x in rows])
def update_card(cid,**kw):
    allowed=['front','back','hint','tags','english','spanish','kind','options','explanation']; vals=[]; sets=[]
    for k in allowed:
        if k in kw and kw[k] is not None: sets.append(k+'=?'); vals.append(json.dumps(kw[k]) if k=='options' else kw[k])
    if not sets:return err('No fields to update')
    with conn() as c: vals.append(cid); n=c.execute('update cards set '+','.join(sets)+' where id=?',vals).rowcount; return ok({'id':cid},'Card updated') if n else err('Card not found')
def delete_card(cid):
    with conn() as c:n=c.execute('delete from cards where id=?',(cid,)).rowcount; return ok({'deleted':n},'Card deleted') if n else err('Card not found')
def review(cid,rating):
    intervals={'again':0,'hard':1,'good':3,'easy':7};
    with conn() as c:
        x=c.execute('select * from cards where id=?',(cid,)).fetchone()
        if not x:return err('Card not found')
        success=rating!='again'; interval=intervals.get(rating,3); due=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=interval)).isoformat(); ease=max(1.3,x['ease']+({'easy':.15,'hard':-.15,'again':-.25}.get(rating,0))); c.execute('update cards set due_at=?,interval=?,ease=?,successes=successes+?,lapses=lapses+? where id=?',(due,interval,ease,int(success),int(not success),cid)); c.execute('insert into reviews(card_id,rating,reviewed_at,correct) values(?,?,?,?)',(cid,rating,now(),int(success))); c.execute('insert into activity(kind,detail,happened_at) values(?,?,?)',('review',rating,now())); return ok({'card_id':cid,'next_due':due,'interval':interval},'Review recorded')
def due():
    with conn() as c:return ok([card(x) for x in c.execute('select * from cards where due_at is null or due_at<=? order by due_at',(now(),))])
def progress():
    with conn() as c:
        total=c.execute('select count(*) from cards').fetchone()[0]; reviewed=c.execute('select count(*) from reviews').fetchone()[0]; correct=c.execute('select coalesce(sum(correct),0) from reviews').fetchone()[0]; mastered=c.execute('select count(*) from cards where interval>=7').fetchone()[0]; return ok({'total_cards':total,'reviewed':reviewed,'accuracy':round(correct/reviewed*100,1) if reviewed else 0,'mastered':mastered,'due':len(due()['data'])})
def quiz(did,limit=10):
    cards=list_cards(did)['data']; random.shuffle(cards); qs=[]
    for x in cards[:limit]: qs.append({'card_id':x['id'],'type':x['kind'],'question':x['front'],'options':x['options'] or [x['back']],'answer':x['back']})
    return ok({'questions':qs,'warning':'Too few cards for a varied quiz' if len(qs)<3 else None},'Quiz generated')
def export_deck(did,fmt='json'):
    d=get_deck(did)['data']; cards=list_cards(did)['data'];
    if fmt=='csv':
        out=io.StringIO(); w=csv.DictWriter(out,fieldnames=['front','back','hint','tags','english','spanish','kind','options','explanation']); w.writeheader(); [w.writerow({k:x.get(k,'') for k in w.fieldnames}) for x in cards]; return ok(out.getvalue(),'CSV exported')
    return ok(json.dumps({'title':d['title'],'description':d['description'],'cards':cards},ensure_ascii=False,indent=2),'JSON exported')
def import_deck(payload,fmt='json'):
    try:
        obj=json.loads(payload) if fmt=='json' else {'title':'Imported deck','description':'','cards':list(csv.DictReader(io.StringIO(payload)))}
        r=create_deck(obj['title'],obj.get('description',''))
        if not r['success']:return r
        for x in obj.get('cards',[]):
            if not x.get('front') or not x.get('back'): return err('Invalid import: every card needs front and back')
            create_card(r['data']['id'],**{k:x.get(k,'') for k in ['front','back','hint','tags','english','spanish','kind','explanation']},options=x.get('options',[]))
        return r
    except Exception as e:return err('Invalid import: '+str(e))
