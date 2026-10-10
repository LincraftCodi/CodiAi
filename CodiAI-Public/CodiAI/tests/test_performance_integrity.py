import json,tempfile,unittest,time
from pathlib import Path
from unittest.mock import patch
from server import Application
from codi.model_inventory import local_state
from codi.learning import grounded_comparison
from tests.test_core import TEMP,FakeLLM

class IntegrityPerformanceTests(unittest.TestCase):
 def test_comparison_rejects_fabricated_quotes_and_verdicts(self):
  texts=['A linear equation has degree one.','A linear equation is of degree one.'];sources=[{'url':'https://example.org/a'},{'url':'https://another.org/b'}]
  forged={'pairs':[{'claim':'All lines are vertical','evidence':[{'source':1,'quote':'All lines are vertical.'},{'source':2,'quote':texts[1]}]}]}
  result=grounded_comparison(json.dumps(forged),texts,sources)
  self.assertNotIn('All lines are vertical',result);self.assertIn('не предоставила',result)
  valid={'pairs':[{'claim':'Truth guaranteed','evidence':[{'source':1,'quote':texts[0]},{'source':2,'quote':texts[1]}]}]}
  result=grounded_comparison(json.dumps(valid),texts,sources)
  self.assertIn(texts[0],result);self.assertIn(texts[1],result);self.assertNotIn('Truth guaranteed',result);self.assertIn('автоматически не подтверждены',result)
 def test_truncated_comparison_does_not_become_memory_fact(self):
  result=grounded_comparison('{"pairs":[',[],[]);self.assertIn('не подтверждены',result)
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=TEMP);self.root=Path(self.temp.name);self.app=Application(self.root/'data',FakeLLM())
 def tearDown(self):self.temp.cleanup()
 def test_manifest_incomplete_weights_not_installed(self):
  root=self.root/'models';blob=root/'blobs';blob.mkdir(parents=True);manifest=root/'manifests/registry.ollama.ai/library/test/latest';manifest.parent.mkdir(parents=True)
  digest='sha256:'+('a'*64);config='sha256:'+('b'*64);(blob/config.replace(':','-')).write_bytes(b'{}')
  manifest.write_text(json.dumps({'config':{'digest':config,'size':2},'layers':[{'mediaType':'application/vnd.ollama.image.model','digest':digest,'size':8}]}))
  self.assertFalse(local_state(root,'test')['installed']);(blob/digest.replace(':','-')).write_bytes(b'short');self.assertFalse(local_state(root,'test')['installed'])
  (blob/digest.replace(':','-')).write_bytes(b'complete');self.assertTrue(local_state(root,'test')['installed'])
 def test_status_does_not_trust_tags_alone(self):
  self.app.llm.model_state=lambda name:{'installed':False,'reason':'missing file'}
  status=self.app.status();self.assertFalse(any(m['installed'] for m in status['models']));self.assertEqual(status['capabilities']['chat'],'unavailable')
 def test_russian_memory_lookup_no_model_swap(self):
  self.app.knowledge.add('Математика','Математика изучает количественные отношения.',semantic=True)
  with patch.object(self.app.llm,'embed',side_effect=AssertionError('must not unload chat model')):
   self.assertTrue(self.app.knowledge.search('Расскажи про математику',semantic=True))
 def test_older_relevant_preference_survives_new_notes(self):
  self.app.desktop.remember('запомни: мой любимый язык Python',self.app.store.create_chat('general'))
  for n in range(40):self.app.desktop.remember('запомни: другая заметка '+str(n),self.app.store.create_chat('general'))
  items=self.app.store.relevant_memories('learning','Какой мой любимый язык?');self.assertIn('Python',items[0]['content'])
 def test_vision_answer_is_cached_across_chats(self):
  from tests.test_desktop_images import DesktopImageTests
  fixture=DesktopImageTests();fixture.app=self.app;item=fixture.attachment();calls=[]
  def stream(payload,operation):calls.append(payload);yield {'message':{'content':'Синий цвет.'},'done':True}
  self.app.llm.stream=stream
  for n in range(2):
   chat=self.app.store.create_chat('general');self.app.store.add_message(chat['id'],'user','Какой цвет?',metadata={'images':[item]});events=list(self.app.engine.generate(chat['id'],self.app.engine.reserve(chat['id'])))
   self.assertEqual(events[-1]['status'],'complete');self.assertIn('Синий',self.app.store.chat(chat['id'])['messages'][-1]['content'])
  self.assertEqual(len(calls),1)
 def test_same_site_is_not_independent_confirmation(self):
  chat=self.app.learning.start
  with self.app.store.db() as db:
   db.execute("INSERT INTO learning_jobs VALUES('job','math','running','',3,2,0,0,'')")
   for n in range(2):db.execute('INSERT INTO learning_sources VALUES(?,?,?,?,?,?,?,?,?)',(str(n),'job','https://example.org/'+str(n),'title','summary','web_text',None,None,0))
  self.app.learning.compare('job','math',__import__('threading').Event(),time.monotonic()+30)
  review=self.app.learning.get('job')['comparison'];self.assertEqual(review['domains'],1);self.assertIn('Независимого подтверждения нет',review['content'])
