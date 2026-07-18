import os,tempfile
os.environ['STUDY_DATA_DIR']=tempfile.mkdtemp()
from local_study_app import service
def test_seed_and_crud():
    d=service.list_decks(); assert len(d['data'])==2
    x=service.create_deck('Test'); assert x['success']; c=service.create_card(x['data']['id'],'Q','A'); assert c['success']; assert len(service.list_cards(x['data']['id'])['data'])==1; assert service.review(c['data']['id'],'good')['success']; assert service.progress()['data']['reviewed']==1
def test_quiz_export_import():
    did=service.list_decks()['data'][0]['id']; assert service.quiz(did)['success']; assert 'front' in service.export_deck(did,'csv')['data']; assert service.import_deck('{"title":"Imported","cards":[{"front":"a","back":"b"}]}')['success']
