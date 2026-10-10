import json,queue,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from server import Application,make_server
from widget import Widget,Client
from codi.research import Research
from codi.engine import Operation
from tests.test_core import TEMP,FakeLLM

class SuperAndWidgetTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=TEMP);self.root=Path(self.tmp.name);self.app=Application(self.root/'data',FakeLLM())
 def tearDown(self):self.tmp.cleanup()
 def test_widget_rename_and_launch_through_http_no_capture_or_context_error(self):
  server=make_server(0,self.app);threading.Thread(target=server.serve_forever,daemon=True).start()
  try:
   file=self.root/'original.txt';file.write_text('keep me',encoding='utf-8')
   w=Widget.__new__(Widget);w.client=Client('http://127.0.0.1:'+str(server.server_port));w.context={'file':str(file)};w.images=[];w.chat=None;w.busy=False;w.capturing=False;w.session_path=self.root/'session.json';w.events=queue.Queue()
   w.input=Mock();w.send_button=Mock();w.status=Mock();w.write=Mock();w.see_screen=Mock();w.see_screen.get.return_value=True;w.capture=Mock();w.run_job=lambda work:work()
   w.send('перименуй этот файл в renamed.txt');self.assertEqual((self.root/'renamed.txt').read_text(encoding='utf-8'),'keep me');self.assertFalse(file.exists());w.capture.assert_not_called()
   w.busy=False
   with patch.object(self.app.desktop,'launch',return_value={'reply':'Отправлена команда запуска: Блокнот','action':{'type':'launch','name':'Блокнот'}}) as launch:
    w.send('можешь открыть блокнот');launch.assert_called_once_with('блокнот')
   w.capture.assert_not_called();self.assertFalse(any(kind=='error' for kind,data in w.events.queue))
   self.assertTrue(w.session_path.is_file())
  finally:server.shutdown();server.server_close()
 def test_super_reads_eight_different_sites_not_search_snippets(self):
  candidates=[{'url':'https://site'+str(n)+'.org/a','title':'site'} for n in range(9)];candidates.insert(1,{'url':'https://site0.org/b','title':'duplicate'})
  def read(url):return {'url':url,'title':'Read page','text':'Real page about algebra and equations. '*80}
  research=Research()
  with patch('codi.research.web_sources.search',return_value=candidates),patch('codi.research.web_sources.read_source',side_effect=read) as reader:
   events=list(research.collect('algebra equations',Operation(),8))
  result=events[-1]['value'];self.assertEqual(len(result['sources']),8);self.assertEqual(reader.call_count,8);self.assertTrue(all('Real page' in s['content'] for s in result['sources']))
 def test_super_failure_and_cancellation_are_honest(self):
  research=Research()
  with patch('codi.research.web_sources.search',return_value=[]):result=list(research.collect('query',Operation(),12))[-1]['value']
  self.assertFalse(result['sources']);self.assertIn('не удалось',result['error'])
  op=Operation();op.cancel()
  with patch('codi.research.web_sources.search',return_value=[{'url':'https://site.org/a'}]),patch('codi.research.web_sources.read_source') as reader:list(research.collect('query',op,4));reader.assert_not_called()
 def test_super_context_contains_every_source_and_links_without_tools(self):
  pages=[{'id':str(n),'name':'Site '+str(n),'url':'https://site'+str(n)+'.org/a','position':0,'content':'Evidence '+str(n)+' '+('sample '*180)} for n in range(8)]
  def collect(*args):yield {'type':'research_result','value':{'sources':pages,'error':'','requested':8}}
  self.app.engine.research.collect=collect;calls=[]
  def stream(payload,op):calls.append(payload);yield {'message':{'content':'Answer with evidence [1] and uncertainty.'},'done':True}
  self.app.llm.stream=stream;chat=self.app.store.create_chat('super');self.app.store.add_message(chat['id'],'user','What is algebra?')
  events=list(self.app.engine.generate(chat['id'],self.app.engine.reserve(chat['id'])));self.assertEqual(events[-1]['status'],'complete');self.assertNotIn('tools',calls[0]);self.assertGreaterEqual(calls[0]['options']['num_ctx'],8192)
  for n in range(8):self.assertIn('https://site'+str(n)+'.org/a',calls[0]['messages'][-1]['content'])
  answer=self.app.store.chat(chat['id'])['messages'][-1];self.assertEqual(len(answer['metadata']['sources']),8);self.assertIn('Прочитанные источники',answer['content'])

if __name__=='__main__':unittest.main()
