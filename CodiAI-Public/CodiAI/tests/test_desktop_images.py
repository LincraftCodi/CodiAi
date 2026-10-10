import base64
import io
import tempfile
import http.client
import json
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from server import Application,make_server
from codi.images import VISION_MODEL
from tests.test_core import FakeLLM,TEMP

class DesktopImageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=TEMP);self.root=Path(self.temp.name)
        self.app=Application(self.root/'data',FakeLLM())
    def tearDown(self):self.temp.cleanup()
    def attachment(self):
        output=io.BytesIO();Image.new('RGB',(1600,800),'blue').save(output,'PNG')
        return self.app.images.add('Картинка.png',base64.b64encode(output.getvalue()).decode())
    def test_normalization_and_invalid_images(self):
        item=self.attachment();self.assertEqual((item['width'],item['height']),(1280,640))
        self.assertTrue(self.app.images.bytes(item['id']).startswith(b'\xff\xd8'))
        for value in ('badbase64',base64.b64encode(b'MZfakeexe').decode()):
            with self.assertRaises(ValueError):self.app.images.add('x.png',value)
        with self.assertRaises(ValueError):self.app.images.get('../outside')
        self.assertEqual(len(self.app.store.export()['images']),1)
    def test_vision_stage_and_edit_invalidation(self):
        item=self.attachment();payloads=[]
        def stream(payload,operation):
            payloads.append(payload)
            yield {'message':{'content':'Синий прямоугольник' if payload['model']==VISION_MODEL else 'На картинке синий цвет.'},'done':True}
        self.app.llm.stream=stream
        chat=self.app.store.create_chat('general');mid=self.app.store.add_message(chat['id'],'user','Какой цвет?',metadata={'images':[item]})
        events=list(self.app.engine.generate(chat['id'],self.app.engine.reserve(chat['id'])))
        self.assertEqual(events[-1]['status'],'complete')
        self.assertTrue(payloads[0]['messages'][-1]['images'])
        self.assertEqual(payloads[0]['keep_alive'],'0s')
        self.assertEqual(len(payloads),1)
        self.assertIn('Синий прямоугольник',self.app.store.chat(chat['id'])['messages'][-1]['content'])
        changed=self.app.store.edit_message(chat['id'],mid,'Какой размер?')
        self.assertNotIn('vision',changed['messages'][0]['metadata'])
        self.assertEqual(changed['messages'][0]['metadata']['images'][0]['id'],item['id'])
    def test_autowrite_multiple_files_and_undo(self):
        project=self.root/'project';project.mkdir();(project/'main.py').write_text('value=1\n')
        self.app.store.save_settings({**self.app.store.settings(),'workspace':str(project),'tools_enabled':True,'project_autowrite':True})
        calls=0
        def stream(payload,operation):
            nonlocal calls
            calls+=1
            if calls==1:
                yield {'message':{'tool_calls':[{'function':{'name':'propose_write','arguments':{'path':p,'content':c}}} for p,c in [('main.py','value=2\n'),('nested/settings.json','{"ready": true}')]]},'done':True}
            else:yield {'message':{'content':'Готово.'},'done':True}
        self.app.llm.stream=stream;chat=self.app.store.create_chat('vibecoding');self.app.store.add_message(chat['id'],'user','Сделай два файла')
        events=list(self.app.engine.generate(chat['id'],self.app.engine.reserve(chat['id'])))
        self.assertEqual(events[-1]['status'],'complete')
        self.assertEqual((project/'main.py').read_text(),'value=2\n')
        self.assertTrue((project/'nested/settings.json').exists())
        results=[e['result'] for e in events if e['type']=='tool']
        self.assertTrue(all(r['file_written'] for r in results))
        self.app.tools.undo(results[0]['proposal_id'],str(project))
        self.assertEqual((project/'main.py').read_text(),'value=1\n')
        self.app.tools.undo(results[1]['proposal_id'],str(project))
        self.assertFalse((project/'nested/settings.json').exists())
    def test_bad_syntax_does_not_overwrite(self):
        project=self.root/'project';project.mkdir();path=project/'main.py';path.write_text('value=1\n')
        settings={**self.app.store.settings(),'workspace':str(project),'tools_enabled':True}
        proposed=self.app.tools.execute('propose_write',{'path':'main.py','content':'def broken('},settings)
        with self.assertRaises(SyntaxError):self.app.tools.apply(proposed['proposal_id'],str(project))
        self.assertEqual(path.read_text(),'value=1\n')
    def test_memory_and_replay(self):
        chat=self.app.store.create_chat('desktop');desktop=self.app.desktop
        with patch.object(desktop,'apps',return_value=[{'name':'Блокнот','path':'notepad.exe'}]),patch('os.startfile') as launch:
            result=desktop.command('запусти программу Блокнот',{},chat)
            desktop.record(chat['id'],result['action'],result['reply']);self.app.store.add_message(chat['id'],'assistant',result['reply'],metadata={'desktop_action':result['action']})
            desktop.command('запомни это',{},self.app.store.chat(chat['id']))
            self.assertIn('Порядок действий',self.app.store.memories()[0]['content'])
            desktop.command('сделай как в прошлый раз',{},chat)
            self.assertEqual(launch.call_count,2)
        self.assertTrue(self.app.store.settings()['memory_enabled'])
        self.assertIsNone(desktop.command('Объясни, что значит «удали файл»',{},chat))
        with self.assertRaises(ValueError):desktop.command('удали этот файл',{},chat)
    def test_selected_file_and_ambiguous_program(self):
        path=self.root/'temporary.txt';path.write_text('test');chat=self.app.store.create_chat('desktop')
        with patch.object(self.app.desktop,'recycle',return_value={'reply':'В Корзине','action':None}) as recycle:
            self.app.desktop.command('удали этот файл',{'file':str(path)},chat)
            recycle.assert_called_once_with(path)
        with patch.object(self.app.desktop,'apps',return_value=[{'name':'Editor 1','path':'one'},{'name':'Editor 2','path':'two'}]),patch('os.startfile') as launch:
            self.assertIsNone(self.app.desktop.launch('Editor')['action']);launch.assert_not_called()
    def test_natural_folder_creation_and_rename(self):
        chat=self.app.store.create_chat('desktop')
        with patch.object(self.app.desktop,'desktop_folder',return_value=self.root):
            result=self.app.desktop.command('Сделай мне на рабочем столе папку с названием блюм',{},chat)
            self.assertEqual(result['action']['type'],'mkdir');self.assertTrue((self.root/'блюм').is_dir())
        source=self.root/'old.txt';source.write_text('content')
        self.app.desktop.command('переименуй этот файл в new.txt',{'file':str(source)},chat)
        self.assertEqual((self.root/'new.txt').read_text(),'content');self.assertFalse(source.exists())
        with self.assertRaises(ValueError):self.app.desktop.create_folder('../outside',{'folder':str(self.root)})
        with self.assertRaises(ValueError):self.app.desktop.create_folder('CON',{'folder':str(self.root)})
    def test_http_images_folder_and_direct_memory(self):
        server=make_server(0,self.app);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(path,data):
            client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            client.request('POST',path,json.dumps(data),{'Content-Type':'application/json','X-Codi-Token':self.app.token})
            response=client.getresponse();result=response.status,json.loads(response.read());client.close();return result
        try:
            image=self.attachment()
            status,uploaded=request('/api/images',{'name':'x.jpg','data':self.app.images.encode(image['id'])});self.assertEqual(status,201)
            chat=self.app.store.create_chat('general')
            status,missing=request('/api/chat',{'chat_id':chat['id'],'message':'Что здесь?','images':[uploaded['id']]})
            self.assertEqual(status,400);self.assertFalse(self.app.store.chat(chat['id'])['messages'])
            status,result=request('/api/chat',{'chat_id':chat['id'],'message':'запомни: люблю короткие ответы'})
            self.assertEqual(status,200);self.assertTrue(result['command']);self.assertEqual(len(self.app.store.memories()),1)
            project=self.root/'workspace';project.mkdir()
            with patch.object(self.app.folders,'choose',return_value={'cancelled':False,'path':str(project)}):
                status,result=request('/api/workspace/pick',{});self.assertEqual(status,200)
                self.assertEqual(result['settings']['workspace'],str(project));self.assertTrue(result['settings']['tools_enabled'])
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()


class DirectFileRegressionTests(unittest.TestCase):
    setUp=DesktopImageTests.setUp
    tearDown=DesktopImageTests.tearDown
    def test_general_desktop_default_and_named_files(self):
        chat=self.app.store.create_chat('general');desktop=self.app.desktop
        with patch.object(desktop,'desktop_folder',return_value=self.root):
            result=desktop.command('сделай папку на рабочем столе',{},chat)
            self.assertTrue((self.root/'Новая папка').is_dir())
            self.assertEqual(result['action']['type'],'mkdir')
            desktop.command('создай папку на рабочем столе',{},chat)
            self.assertTrue((self.root/'Новая папка (2)').is_dir())
            result=desktop.command('создай файл заметка.txt на рабочем столе с текстом привет',{},chat)
            self.assertEqual((self.root/'заметка.txt').read_text(encoding='utf-8'),'привет')
            self.assertEqual(desktop.target('заметка.txt на рабочем столе',{}),self.root/'заметка.txt')
            with patch.object(desktop,'recycle',return_value={'reply':'Удалено'}) as recycle:
                desktop.command('удали файл заметка.txt на рабочем столе',{},chat)
                recycle.assert_called_once_with(self.root/'заметка.txt')
            with self.assertRaises(ValueError):desktop.command('создай файл заметка.txt на рабочем столе',{},chat)
    def test_selected_write_backup(self):
        chat=self.app.store.create_chat('desktop');path=self.root/'note.txt';path.write_text('before')
        result=self.app.desktop.command('запиши в этот файл текст: after',{'file':str(path)},chat)
        self.assertEqual(path.read_text(),'after')
        self.assertEqual(Path(result['action']['backup']).read_text(),'before')
