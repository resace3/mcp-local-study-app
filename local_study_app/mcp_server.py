"""Small dependency-free MCP stdio bridge, compatible with Python 3.9."""
import json, sys, subprocess, webbrowser, urllib.request
from . import service
from .db import DB
TOOLS = {
 'list_decks': lambda a: service.list_decks(), 'get_deck':lambda a:service.get_deck(a['deck_id']),
 'create_deck':lambda a:service.create_deck(a['title'],a.get('description','')), 'update_deck':lambda a:service.update_deck(a['deck_id'],a.get('title'),a.get('description')),
 'delete_deck':lambda a:service.delete_deck(a['deck_id']), 'duplicate_deck':lambda a:service.duplicate_deck(a['deck_id'],a.get('title')),
 'list_cards':lambda a:service.list_cards(a['deck_id'],a.get('query','')), 'create_flashcard':lambda a:service.create_card(**a),
 'delete_flashcard':lambda a:service.delete_card(a['card_id']), 'generate_quiz_from_deck':lambda a:service.quiz(a['deck_id'],a.get('limit',10)),
 'record_card_review':lambda a:service.review(a['card_id'],a['rating']), 'get_due_cards':lambda a:service.due(), 'get_study_progress':lambda a:service.progress(),
 'export_deck':lambda a:service.export_deck(a['deck_id'],a.get('format','json')), 'import_deck':lambda a:service.import_deck(a['payload'],a.get('format','json')),
}
NAMES=list(TOOLS)+['start_study_app','open_study_app','get_study_app_status','stop_study_app']
def lifecycle(name):
    if name=='get_study_app_status': return {'success':True,'url':'http://127.0.0.1:8080','database':str(DB)}
    if name=='stop_study_app': return {'success':True,'summary':'Use scripts/stop.ps1 to stop managed web processes'}
    try: urllib.request.urlopen('http://127.0.0.1:8080/api/health',timeout=1); running=True
    except Exception:
        subprocess.Popen([sys.executable,'-m','local_study_app.server'],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)); running='starting'
    r={'success':True,'url':'http://127.0.0.1:8080','running':running,'database':str(DB)}
    if name=='open_study_app': webbrowser.open(r['url'])
    return r
def reply(i,result): return {'jsonrpc':'2.0','id':i,'result':result}
def main():
    for line in sys.stdin:
        try:
            req=json.loads(line); method=req.get('method'); i=req.get('id')
            if method=='initialize': out=reply(i,{'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'local-study-app','version':'1.0.0'}})
            elif method=='notifications/initialized': continue
            elif method=='tools/list': out=reply(i,{'tools':[{'name':n,'description':'Local study app tool','inputSchema':{'type':'object'}} for n in NAMES]})
            elif method=='tools/call':
                n=req['params']['name']; a=req['params'].get('arguments',{}); result=lifecycle(n) if n in NAMES[-4:] else TOOLS[n](a); out=reply(i,{'content':[{'type':'text','text':json.dumps(result,ensure_ascii=False)}],'structuredContent':result})
            else: continue
            sys.stdout.write(json.dumps(out)+'\n'); sys.stdout.flush()
        except Exception as e:
            sys.stdout.write(json.dumps({'jsonrpc':'2.0','id':req.get('id'),'error':{'code':-32000,'message':str(e)}})+'\n'); sys.stdout.flush()
if __name__=='__main__': main()
