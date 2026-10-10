import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server import Application
from codi.screen_tasks import SCREEN_TRANSLATE,SCREEN_ANSWER,needs_screen,reading_image
from codi.desktop_controls import quick_command
from tests.test_core import TEMP,FakeLLM

class ScreenMemoryCommandTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=TEMP);self.root=Path(self.tmp.name);self.app=Application(self.root/'data',FakeLLM());self.chat=self.app.store.create_chat('desktop')
 def tearDown(self):self.tmp.cleanup()
 def test_desktop_context_with_memory_no_undefined_variable(self):
  self.app.desktop.remember('запомни: Меня зовут Иван',self.chat)
  self.app.store.add_message(self.chat['id'],'user','Как меня зовут?')
  context,_=self.app.engine.context(self.app.store.chat(self.chat['id']),self.app.store.settings())
  self.assertIn('Иван',context[0]['content'])
 def test_old_russian_fact_found_after_250_notes(self):
  self.app.desktop.remember('запомни: Любимый город Казань',self.chat)
  for n in range(250):self.app.desktop.remember('запомни: другая заметка '+str(n),self.chat)
  self.assertIn('Казань',self.app.store.relevant_memories('preferences','Какой мой любимый город?')[0]['content'])
  result=self.app.desktop.command('Какой мой любимый город?',{},self.chat);self.assertIn('Казань',result['reply']);self.assertTrue(quick_command('Какой мой любимый город?'))
 def test_folder_word_order_and_new_destination(self):
  with patch.object(self.app.desktop,'desktop_folder',return_value=self.root):
   for command in ['можешь создать новую папку на рабочем столе','создай на рабочем столе папку с названием Архив','сделай мне папку Данные на рабочем столе!']:
    result=self.app.desktop.command(command,{},self.chat);self.assertIsNotNone(result);self.assertTrue(Path(result['action']['path']).is_dir())
   target=self.root/'new-parent'/'new-child'
   result=self.app.desktop.command('создай папку "'+str(target)+'"',{},self.chat);self.assertTrue(target.is_dir())
   result=self.app.tools.execute('desktop_mkdir',{'name':'Инструмент'},{**self.app.store.settings(),'tools_enabled':True});self.assertEqual(result['action']['type'],'mkdir');self.assertTrue((self.root/'Инструмент').is_dir())
 def test_explicit_desktop_folder_in_roleplay(self):
  story=self.app.store.create_chat('roleplay')
  with patch.object(self.app.desktop,'desktop_folder',return_value=self.root):
   self.assertIsNone(self.app.desktop.command('создай папку в сказке',{},story))
   self.assertIsNotNone(self.app.desktop.command('создай папку Реальная на рабочем столе',{},story))
 def test_screen_tasks_one_model_and_readable_resolution(self):
  from tests.test_desktop_images import DesktopImageTests
  fixture=DesktopImageTests();fixture.app=self.app;attachment=fixture.attachment();calls=[]
  def stream(payload,operation):calls.append(payload);yield {'message':{'content':'Перевод / ответ'},'done':True}
  self.app.llm.stream=stream
  for prompt in [SCREEN_TRANSLATE,SCREEN_ANSWER]:
   self.assertTrue(needs_screen(prompt));self.assertTrue(reading_image(prompt))
   chat=self.app.store.create_chat('desktop');self.app.store.add_message(chat['id'],'user',prompt,metadata={'images':[attachment]})
   events=list(self.app.engine.generate(chat['id'],self.app.engine.reserve(chat['id'])))
   self.assertEqual(events[-1]['status'],'complete');self.assertIn(prompt,calls[-1]['messages'][-1]['content']);self.assertEqual(calls[-1]['options']['num_predict'],-1)
  self.assertEqual(len(calls),2)

if __name__=='__main__':unittest.main()
