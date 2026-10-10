import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from server import Application
from codi.screen_tasks import SCREEN_TRANSLATE
from tests.test_core import TEMP,FakeLLM

class OCRTranslationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=TEMP);self.root=Path(self.tmp.name);self.app=Application(self.root/'data',FakeLLM())
 def tearDown(self):self.tmp.cleanup()
 def image(self):
  from tests.test_desktop_images import DesktopImageTests
  fixture=DesktopImageTests();fixture.app=self.app;return fixture.attachment()
 def test_ocr_translation_bypasses_vision_tools_and_uses_cache(self):
  item=self.image();calls=[]
  def stream(payload,operation):calls.append(payload);yield {'message':{'content':'Сохраните работу перед закрытием окна.'},'done':True}
  self.app.llm.stream=stream
  with patch.object(self.app.engine.ocr,'read',return_value={'text':'Save your work before closing this window.','language':'en-US'}):
   for n in range(2):
    chat=self.app.store.create_chat('desktop');self.app.store.add_message(chat['id'],'user',SCREEN_TRANSLATE,metadata={'images':[item]})
    events=list(self.app.engine.generate(chat['id'],self.app.engine.reserve(chat['id'])))
    self.assertEqual(events[-1]['status'],'complete')
  self.assertEqual(len(calls),1);self.assertNotIn('images',calls[0]['messages'][-1]);self.assertNotIn('tools',calls[0]);self.assertIn('Save your work',calls[0]['messages'][-1]['content']);self.assertLessEqual(calls[0]['options']['temperature'],.15)
  self.assertNotIn('/no_think',calls[0]['messages'][-1]['content'])
 def test_question_from_ocr_does_not_get_desktop_action_tools(self):
  item=self.image();calls=[]
  def stream(payload,operation):calls.append(payload);yield {'message':{'content':'B — 12.'},'done':True}
  self.app.llm.stream=stream
  with patch.object(self.app.engine.ocr,'read',return_value={'text':'What is 7 + 5? A.10 B.12','language':'en-US'}):
   chat=self.app.store.create_chat('desktop');self.app.store.add_message(chat['id'],'user','Ответь на вопрос на экране',metadata={'images':[item]})
   events=list(self.app.engine.generate(chat['id'],self.app.engine.reserve(chat['id'])))
  self.assertEqual(events[-1]['status'],'complete');self.assertEqual(len(calls),1)
  self.assertFalse(any(s['function']['name'].startswith('desktop_') for s in calls[0].get('tools',[])))
 def test_missing_ocr_falls_back_to_vision(self):
  item=self.image();calls=[]
  def stream(payload,operation):calls.append(payload);yield {'message':{'content':'Перевод с картинки'},'done':True}
  self.app.llm.stream=stream
  with patch.object(self.app.engine.ocr,'read',return_value=None):
   chat=self.app.store.create_chat('desktop');self.app.store.add_message(chat['id'],'user',SCREEN_TRANSLATE,metadata={'images':[item]})
   events=list(self.app.engine.generate(chat['id'],self.app.engine.reserve(chat['id'])))
  self.assertEqual(events[-1]['status'],'complete');self.assertEqual(len(calls),1);self.assertTrue(calls[0]['messages'][-1]['images'])
 def test_greeting_does_not_load_embeddings_or_retrieve_stopwords(self):
  self.app.knowledge.add('Алгебра','Это описание: как и что изучать в алгебре.',semantic=True)
  with patch.object(self.app.llm,'embed',side_effect=AssertionError('chat must stay loaded')):
   chat=self.app.store.create_chat('desktop');self.app.store.add_message(chat['id'],'user','Привет')
   _,sources=self.app.engine.context(self.app.store.chat(chat['id']),self.app.store.settings());self.assertEqual(sources,[])
   self.assertEqual(self.app.knowledge.search('что это',semantic=True),[])
