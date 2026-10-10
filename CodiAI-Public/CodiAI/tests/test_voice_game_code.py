import json,threading,types,unittest
from unittest.mock import Mock,patch
from tests import test_super_and_widget_actions as fixtures
from codi.game import GameInput,valid_action
from codi.voice import Voice
from codi.project_build import build
from codi.tools import safe_path

class VoiceGameCodeTests(unittest.TestCase):
 setUp=fixtures.SuperAndWidgetTests.setUp
 tearDown=fixtures.SuperAndWidgetTests.tearDown
 def test_chatgpt_ignores_old_folder_and_spelling(self):
  chat=self.app.store.create_chat('desktop')
  with patch('webbrowser.open',return_value=True) as opener,patch('codi.web_sources.public_url',side_effect=lambda u:(u,[])):
   for text in ('открой чат гпт','можешь открыть ChatGPT','отрыть чатгпт'):
    result=self.app.desktop.command(text,{'folder':str(self.root/'stale')},chat)
    self.assertEqual(result['action']['type'],'website')
   self.assertEqual(opener.call_count,3)
 def test_create_folder_then_open_uses_new_folder_not_old_file(self):
  chat=self.app.store.create_chat('desktop')
  with patch('codi.desktop.os.startfile') as launch:
   result=self.app.desktop.command('создай папку Пример и открой её',{'folder':str(self.root),'file':str(self.root/'old.txt')},chat)
  self.assertTrue((self.root/'Пример').is_dir());launch.assert_called_once_with(str(self.root/'Пример'))
  self.assertEqual(result['context'],{'folder':str(self.root/'Пример')})
 def test_real_python_project_check_and_binary_apk_rejection(self):
  (self.root/'test_generated.py').write_text('import unittest\nclass Test(unittest.TestCase):\n def test_add(self):self.assertEqual(2+2,4)\n',encoding='utf-8')
  result=build(str(self.root),'python-test');self.assertTrue(result['success']);self.assertIn('OK',result['output'])
  with self.assertRaises(ValueError):build(str(self.root),'android')
  with self.assertRaises(ValueError):safe_path(str(self.root),'fake.apk')
 def test_voice_partial_final_and_cleanup_without_recording_user(self):
  voice=Voice();voice.model=object();voice.state['active']=True
  class Recognizer:
   def __init__(self,*args):pass
   def AcceptWaveform(self,data):voice.cancel.set();return True
   def Result(self):return json.dumps({'text':'привет коди'})
   def FinalResult(self):return json.dumps({'text':''})
  class Stream:
   def __init__(self,**kw):self.callback=kw['callback']
   def __enter__(self):self.callback(b'\0'*8000,4000,None,None);return self
   def __exit__(self,*args):pass
  with patch.dict('sys.modules',{'vosk':types.SimpleNamespace(Model=Mock(),KaldiRecognizer=Recognizer,SetLogLevel=Mock()),'sounddevice':types.SimpleNamespace(RawInputStream=Stream,query_devices=lambda *a,**k:({'name':'Test mic','default_samplerate':48000,'max_input_channels':1,'hostapi':0} if k or a else [{'name':'Test mic','default_samplerate':48000,'max_input_channels':1,'hostapi':0}]),query_hostapis=lambda:[{'name':'Windows WASAPI'}])}):voice.record()
  self.assertFalse(voice.status()['active']);self.assertEqual(voice.status()['text'],'привет коди');self.assertFalse(voice.status()['error'])
 def test_game_key_release_and_focus_guard_without_live_inputs(self):
  adapter=GameInput();adapter.emit=Mock();adapter.focused=Mock(return_value=True);cancel=threading.Event();cancel.set()
  adapter.act(1,valid_action({'keys':['w'],'click':'left'}),cancel)
  adapter.focused.return_value=False
  with self.assertRaises(ValueError):adapter.act(1,valid_action({'keys':['w']}),threading.Event())
  adapter.emit.assert_not_called()
  adapter.focused.return_value=True;cancel=Mock();cancel.is_set.return_value=False;cancel.wait.return_value=True
  adapter.act(1,valid_action({'keys':['w'],'seconds':.2,'click':'left'}),cancel)
  self.assertIn((( 'key',0x57),{'up':True}),[(c.args,c.kwargs) for c in adapter.emit.call_args_list])
  self.assertEqual(adapter.emit.call_args_list[-1].args,('mouse',4))
  with self.assertRaises(ValueError):valid_action({'keys':['alt','f4']})
 def test_game_loop_uses_learned_notes_and_releases_model(self):
  game=self.app.game;game.input=Mock();game.input.focused.return_value=True;game.frame=Mock(return_value='synthetic-image');game.cancel=Mock();game.cancel.wait.return_value=False;game.cancel.is_set.return_value=False
  self.app.knowledge.add('ULTRAKILL управление','ULTRAKILL: W движение вперёд, пробел прыжок.',semantic=False)
  calls=[]
  def stream(payload,op):calls.append(payload);yield {'message':{'content':'{"keys":[],"done":true}'},'done':True}
  self.app.llm.stream=stream;game.run(123,'пройди уровень','ULTRAKILL')
  self.assertIn('ULTRAKILL',calls[0]['messages'][1]['content']);game.input.act.assert_not_called();self.assertFalse(self.app.engine.active);self.assertFalse(game.status()['active'])
 def test_game_target_is_selected_and_not_tied_to_ultrakill(self):
  items=[{'id':10,'title':'Minecraft','process':'javaw','minimized':False},{'id':11,'title':'Another Game','process':'game','minimized':False},{'id':12,'title':'Codex','process':'codex','minimized':False}]
  with patch('codi.game.windows',return_value=items),patch('codi.game.threading.Thread'):
   self.assertEqual(len(self.app.game.available()),2)
   with self.assertRaises(ValueError):self.app.game.start('Иди к выходу')
   result=self.app.game.start('Иди к выходу',11)
   self.assertTrue(result['active'])
 def test_find_tutorials_is_normalized_to_game_controls(self):
  with patch('codi.learning.threading.Thread'):
   job=self.app.learning.start({'topic':'найди сайты и туториалы по Minecraft и научись управлению','minutes':3,'max_pages':4})
  self.assertEqual(job['topic'],'Minecraft управление клавиши руководство')

if __name__=='__main__':unittest.main()
