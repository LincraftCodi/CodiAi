import unittest
from pathlib import Path
from unittest.mock import patch
from tests import test_super_and_widget_actions as fixtures
from codi.tools import safe_path
from codi.file_results import receipts

class FileReliabilityTests(unittest.TestCase):
 setUp=fixtures.SuperAndWidgetTests.setUp
 tearDown=fixtures.SuperAndWidgetTests.tearDown
 def configure(self,**extra):
  self.app.store.save_settings({'workspace':str(self.root),'tools_enabled':True,'project_autowrite':True,**extra});return self.app.store.settings()
 def generate(self,turns,text='Создай HTML-файл с игрой',context=None):
  self.configure();chat=self.app.store.create_chat('vibecoding')
  self.app.store.add_message(chat['id'],'user',text,metadata={'desktop_context':context or {}})
  calls=[]
  def stream(payload,op):
   calls.append(payload);value=turns[min(len(calls)-1,len(turns)-1)]
   if callable(value):value=value()
   yield {'message':value,'done':True}
  self.app.llm.stream=stream
  events=list(self.app.engine.generate(chat['id'],self.app.engine.reserve(chat['id'])))
  return self.app.store.chat(chat['id'])['messages'][-1],calls,events
 def tool(self,name,**arguments):return {'tool_calls':[{'function':{'name':name,'arguments':arguments}}]}
 def test_false_success_without_tools_is_not_displayed(self):
  answer,calls,_=self.generate([{'content':'Файл index.html создан в папке. Готов к использованию!'}])
  self.assertEqual(len(calls),2);self.assertIn('не подтверждено',answer['content']);self.assertNotIn('Готов к использованию',answer['content']);self.assertFalse((self.root/'index.html').exists())
 def test_false_claim_is_retried_then_real_file_and_exact_path_confirmed(self):
  answer,calls,_=self.generate([{'content':'Файл index.html создан.'},self.tool('propose_write',path='nested/index.html',content='<h1>Игра</h1>'),{'content':'Файл missing.html создан в другой папке!'}])
  target=self.root/'nested/index.html';self.assertEqual(target.read_text(encoding='utf-8'),'<h1>Игра</h1>');self.assertIn(str(target),answer['content']);self.assertNotIn('missing.html',answer['content']);self.assertEqual(answer['metadata']['desktop_context']['file'],str(target))
 def test_absolute_path_within_project_is_normalized_but_outside_rejected(self):
  settings=self.configure();target=self.root/'проект/index.html'
  result=self.app.tools.execute('propose_write',{'path':str(target),'content':'<html></html>'},settings)
  self.assertFalse(target.exists());applied=self.app.tools.apply(result['proposal_id'],str(self.root))
  self.assertTrue(applied['file_written']);self.assertTrue(applied['read_back_verified']);self.assertEqual(applied['absolute_path'],str(target));self.assertEqual(target.read_text(),'<html></html>')
  with self.assertRaises(ValueError):safe_path(str(self.root),str(self.root.parent/'outside.html'))
 def test_in_that_folder_creates_in_selected_subfolder_not_project_root(self):
  folder=self.root/'проект';folder.mkdir()
  answer,_,_=self.generate([self.tool('propose_write',path='index.html',content='game'),{'content':'HTML-файл создан.'}],'В ней создай HTML-файл с игрой',{'folder':str(folder)})
  self.assertTrue((folder/'index.html').is_file());self.assertFalse((self.root/'index.html').exists());self.assertIn(str(folder/'index.html'),answer['content']);self.assertEqual(self.app.store.settings()['workspace'],str(self.root))
 def test_root_change_during_generation_prevents_wrong_directory_write(self):
  other=self.root/'other';other.mkdir()
  def change():
   self.app.store.save_settings({'workspace':str(other)})
   return self.tool('propose_write',path='index.html',content='wrong')
  answer,_,_=self.generate([change,{'content':'Файл index.html создан.'}])
  self.assertFalse((other/'index.html').exists());self.assertFalse((self.root/'index.html').exists());self.assertIn('не подтверждено',answer['content'])
 def test_file_deleted_before_final_answer_is_not_confirmed(self):
  def remove():
   (self.root/'index.html').unlink();return {'content':'Файл index.html создан.'}
  answer,_,_=self.generate([self.tool('propose_write',path='index.html',content='game'),remove])
  self.assertIn('Не удалось подтвердить',answer['content']);self.assertNotIn('Файлы записаны:',answer['content'])
 def test_multiple_writes_of_same_file_verify_latest_contents(self):
  answer,_,_=self.generate([self.tool('propose_write',path='index.html',content='first'),self.tool('propose_write',path='index.html',content='second'),{'content':'Файл index.html создан.'}])
  self.assertEqual((self.root/'index.html').read_text(),'second');self.assertIn('Файлы записаны:',answer['content']);self.assertNotIn('Не удалось',answer['content'])
 def test_failed_write_cannot_report_success(self):
  answer,_,_=self.generate([self.tool('propose_write',path='../outside.html',content='bad'),{'content':'Файл outside.html создан.'}])
  self.assertIn('не подтверждено',answer['content']);self.assertNotIn('outside.html создан',answer['content'])

 def test_file_description_is_not_used_as_name_of_empty_file(self):
  self.configure();chat=self.app.store.create_chat('vibecoding')
  for text in ('создай html файл с простенькой игрой','создай html файл index.html с кнопкой','создай файл index.html который покажет игру'):
   self.assertIsNone(self.app.desktop.command(text,{'folder':str(self.root)},chat))
  self.assertFalse((self.root/'с простенькой игрой.html').exists())
  result=self.app.desktop.command('создай html файл «с простой игрой»',{'folder':str(self.root)},chat)
  self.assertTrue((self.root/'с простой игрой.html').exists())

 def test_mkdir_existing_project_root_is_idempotent(self):
  settings=self.configure()
  result=self.app.tools.execute('project_mkdir',{'path':str(self.root)},settings)
  self.assertEqual(result['absolute_path'],str(self.root));self.assertFalse(result['created'])

if __name__=='__main__':unittest.main()
