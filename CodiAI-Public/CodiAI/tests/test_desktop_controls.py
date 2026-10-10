import tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from server import Application
from tests.test_core import FakeLLM,TEMP
from codi.desktop_controls import clean_command,quick_command,window_action

class ControlTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=TEMP);self.root=Path(self.temp.name);self.app=Application(self.root/'data',FakeLLM());self.chat=self.app.store.create_chat('desktop')
 def tearDown(self):self.temp.cleanup()
 def test_natural_alias_launch(self):
  apps=[{'name':'Google Chrome','path':'chrome.lnk'},{'name':'Блокнот','path':'notepad.exe'}]
  with patch.object(self.app.desktop,'apps',return_value=apps),patch('os.startfile') as launch:
   for text in ('можешь открыть хром','пожалуйста, включи хром','запусти приложение хром'):
    self.assertTrue(quick_command(text));self.assertEqual(self.app.desktop.command(text,{},self.chat)['action']['type'],'launch')
   self.assertEqual(launch.call_count,3)
 def test_rename_named_preserves_extension_and_refuses_collision(self):
  path=self.root/'old.txt';path.write_text('data');context={'folder':str(self.root)}
  result=self.app.desktop.command('переименовать файл old.txt в new',context,self.chat)
  self.assertFalse(path.exists());self.assertEqual((self.root/'new.txt').read_text(),'data')
  self.assertEqual(result['context']['file'],str(self.root/'new.txt'))
  (self.root/'occupied.txt').write_text('keep')
  with self.assertRaises(ValueError):self.app.desktop.command('переименуй new.txt в occupied.txt',context,self.chat)
 def test_copy_move_no_overwrite(self):
  source=self.root/'x.txt';source.write_text('value');destination=self.root/'to';destination.mkdir();context={'folder':str(self.root)}
  self.app.desktop.command('скопируй файл x.txt в папку to',context,self.chat)
  self.assertTrue(source.exists());self.assertEqual((destination/'x.txt').read_text(),'value')
  with self.assertRaises(ValueError):self.app.desktop.command('перемести файл x.txt в папку to',context,self.chat)
  source2=self.root/'y.txt';source2.write_text('other')
  self.app.desktop.command('перенеси файл y.txt в папку to',context,self.chat);self.assertFalse(source2.exists());self.assertTrue((destination/'y.txt').exists())
 def test_copy_directory_into_self_and_links_blocked(self):
  source=self.root/'dir';source.mkdir();child=source/'child';child.mkdir()
  with self.assertRaises(ValueError):self.app.desktop.copy_move(str(source),str(child),{})
 def test_ambiguous_windows_never_act(self):
  inventory=[{'id':1,'title':'Chrome one','process':'chrome'},{'id':2,'title':'Chrome two','process':'chrome'}]
  result=window_action('close','хром',inventory);self.assertNotIn('action',result);self.assertIn('Уточните',result['reply'])
 def test_desktop_tools_work_without_project(self):
  calls=[]
  def stream(payload,operation):
   names=[s['function']['name'] for s in payload['tools']];self.assertIn('desktop_launch',names)
   if not calls:
    calls.append(1);yield {'message':{'tool_calls':[{'function':{'name':'desktop_launch','arguments':{'name':'Блокнот'}}}]},'done':True}
   else:yield {'message':{'content':'Команда запуска отправлена.'},'done':True}
  self.app.llm.stream=stream;self.app.store.add_message(self.chat['id'],'user','Мне нужен Блокнот, запусти его')
  with patch.object(self.app.desktop,'launch',return_value={'reply':'Запуск отправлен'}) as launch:
   events=list(self.app.engine.generate(self.chat['id'],self.app.engine.reserve(self.chat['id'])))
   launch.assert_called_once_with('Блокнот');self.assertEqual(events[-1]['status'],'complete')

 def test_localized_window_title_and_64bit_handle(self):
  user=Mock();user.ShowWindowAsync.return_value=True
  with patch('ctypes.WinDLL',return_value=user):
   result=window_action('minimize','калькулятор',[{'id':4294967297,'title':'Калькулятор','process':'ApplicationFrameHost'}])
   self.assertEqual(result['action']['operation'],'minimize');user.ShowWindowAsync.assert_called_once_with(4294967297,6)

 def test_frequent_typos_stay_direct_commands(self):
  self.assertEqual(clean_command('перименуй этот файл в new.txt'),'переименуй этот файл в new.txt')
  self.assertTrue(quick_command('запусти пожалуйста калькулятор'))
  with patch.object(self.app.desktop,'desktop_folder',return_value=self.root):
   result=self.app.desktop.command('Создай файл на рабочем столе с нащзванием документосы',{},self.chat)
   self.assertEqual(Path(result['action']['path']).name,'документосы')
