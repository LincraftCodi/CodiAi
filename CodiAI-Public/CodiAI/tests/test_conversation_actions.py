import json,threading,unittest
from unittest.mock import patch
from tests import test_super_and_widget_actions as fixtures
from server import make_server,Application
from widget import Client

class ConversationActionTests(unittest.TestCase):
 setUp=fixtures.SuperAndWidgetTests.setUp
 tearDown=fixtures.SuperAndWidgetTests.tearDown
 def test_http_create_rename_reopen_chat_and_open_without_client_context(self):
  server=make_server(0,self.app);threading.Thread(target=server.serve_forever,daemon=True).start()
  client=Client('http://127.0.0.1:'+str(server.server_port))
  self.app.store.save_settings({'workspace':str(self.root)})
  chat=self.app.store.create_chat('general')
  try:
   client.request('/api/chat',{'chat_id':chat['id'],'message':'сделай папку с названием «Проект»'})
   self.assertTrue((self.root/'Проект').is_dir())
   result=client.request('/api/chat',{'chat_id':chat['id'],'message':'теперь переименуй её в с названием «Готово»'})
   self.assertEqual(result['desktop_context']['folder'],str(self.root/'Готово'));self.assertTrue((self.root/'Готово').is_dir())
   restored=Application(self.root/'data',self.app.llm)
   saved=restored.store.chat(chat['id'])
   with patch('codi.desktop.os.startfile') as opener:restored.desktop.command('а теперь открой её',{},saved)
   opener.assert_called_once_with(str(self.root/'Готово'))
   self.assertFalse((self.root/'Проект').exists())
  finally:server.shutdown();server.server_close()
 def test_legacy_action_in_history_restores_folder(self):
  folder=self.root/'legacy';folder.mkdir();chat=self.app.store.create_chat('desktop')
  self.app.store.add_message(chat['id'],'assistant','Создано',metadata={'desktop_action':{'type':'mkdir','path':str(folder)}})
  result=self.app.desktop.command('теперь переименуй её в Новая',{},self.app.store.chat(chat['id']))
  self.assertTrue((self.root/'Новая').is_dir());self.assertEqual(result['context']['folder'],str(self.root/'Новая'))
 def test_clarification_stops_tools_and_persists_choices_with_tools_disabled(self):
  chat=self.app.store.create_chat('vibecoding');calls=[]
  def stream(payload,operation):
   calls.append(payload)
   yield {'message':{'tool_calls':[{'function':{'name':'ask_user','arguments':{'question':'Какой интерфейс?','choices':'Светлый\nТёмный'}}},{'function':{'name':'project_mkdir','arguments':{'path':'unrequested'}}}]},'done':True}
  self.app.llm.stream=stream
  self.app.store.add_message(chat['id'],'user','Хочу выбрать интерфейс')
  events=list(self.app.engine.generate(chat['id'],self.app.engine.reserve(chat['id'])))
  self.assertEqual(len(calls),1);self.assertTrue(any(e['type']=='question' for e in events))
  final=self.app.store.chat(chat['id'])['messages'][-1]
  self.assertEqual(final['metadata']['question']['options'],['Светлый','Тёмный']);self.assertEqual(final['status'],'complete');self.assertFalse((self.root/'unrequested').exists())
 def test_engine_receives_last_created_folder_as_current_object(self):
  folder=self.root/'Проект';folder.mkdir();chat=self.app.store.create_chat('general')
  self.app.store.add_message(chat['id'],'assistant','Создана папка',metadata={'desktop_context':{'folder':str(folder)}})
  self.app.store.add_message(chat['id'],'user','Что ты создала?')
  messages,_=self.app.engine.context(self.app.store.chat(chat['id']),self.app.store.settings())
  self.assertIn(json.dumps(str(folder),ensure_ascii=False),messages[0]['content'])

 def test_long_chat_keeps_original_request_despite_large_code_answers(self):
  chat=self.app.store.create_chat('programmer')
  self.app.store.add_message(chat['id'],'user','Нужен редактор заметок с сохранением на диск')
  for n in range(7):
   self.app.store.add_message(chat['id'],'assistant','Длинный код: '+('x'*1500))
   self.app.store.add_message(chat['id'],'user','Измени цвет '+str(n))
  messages,_=self.app.engine.context(self.app.store.chat(chat['id']),self.app.store.settings())
  self.assertIn('редактор заметок с сохранением на диск',messages[0]['content'])

 def test_coding_request_with_and_run_is_not_swallowed_by_desktop_parser(self):
  chat=self.app.store.create_chat('vibecoding')
  for text in ('Исправь ошибку в calculator.py и запусти python-test','Создай красивый сайт и запусти тесты'):
   self.assertIsNone(self.app.desktop.command(text,{},chat))

 def test_model_created_project_folder_can_be_renamed_in_next_turn(self):
  self.app.store.save_settings({'workspace':str(self.root),'tools_enabled':True})
  chat=self.app.store.create_chat('vibecoding');calls=[]
  def stream(payload,operation):
   calls.append(payload)
   if len(calls)==1:yield {'message':{'tool_calls':[{'function':{'name':'project_mkdir','arguments':{'path':'Создано моделью'}}}]},'done':True}
   else:yield {'message':{'content':'Создала папку.'},'done':True}
  self.app.llm.stream=stream;self.app.store.add_message(chat['id'],'user','Создай папку проекта')
  list(self.app.engine.generate(chat['id'],self.app.engine.reserve(chat['id'])))
  self.app.desktop.command('теперь переименуй её в Готово',{},self.app.store.chat(chat['id']))
  self.assertTrue((self.root/'Готово').is_dir())

if __name__=='__main__':unittest.main()
