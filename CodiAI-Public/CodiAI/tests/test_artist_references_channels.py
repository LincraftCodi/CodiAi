import json,threading,time,unittest
from unittest.mock import patch
from pathlib import Path
from tests import test_core as fixture
from codi.engine import Operation
from codi.asset_checks import check_svg,check_obj
from codi.reference_library import ReferenceLibrary,REFERENCES
from codi import web_sources

SVG='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="40" fill="#5686ff"/></svg>'
OBJ='v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n'
PAGE={'url':'https://docs.python.org/3/tutorial/controlflow.html','title':'Python','text':'Python functions and control flow. '*60,'method':'web_text','links':[]}
class FeatureTests(unittest.TestCase):
 setUp=fixture.CoreTests.setUp
 tearDown=fixture.CoreTests.tearDown
 def finish(self,ident):
  deadline=time.monotonic()+5
  while time.monotonic()<deadline:
   if ident not in self.app.learning.active:return self.app.learning.get(ident)
   time.sleep(.01)
  self.fail('Study did not finish')
 def test_channel_and_new_youtube_renderer(self):
  data={'contents':[{'lockupViewModel':{'contentType':'LOCKUP_CONTENT_TYPE_VIDEO','contentId':'abcdefghijk','metadata':{'lockupMetadataViewModel':{'title':{'content':'Lesson one'}}}}},{'videoRenderer':{'videoId':'lmnopqrstuv','title':{'runs':[{'text':'Lesson two'}]}}}]}
  with patch('codi.web_sources.fetch',return_value=('https://www.youtube.com/@sample/videos','var ytInitialData = '+json.dumps(data)+';','text/html')):
   rows=web_sources.channel_sources('https://www.youtube.com/@sample?si=share')
   self.assertEqual(len(rows),2);self.assertEqual(rows[0]['title'],'Lesson one')
   self.assertIsNone(web_sources.video_id('https://www.youtube.com/@sample'))
   self.assertEqual(web_sources.read_source('https://www.youtube.com/@sample')['method'],'youtube_collection')
 def test_channel_skips_unavailable_video_and_can_resume(self):
  sources=[{'url':'https://www.youtube.com/watch?v='+i,'title':'Lesson '+str(n)} for n,i in enumerate(['abcdefghijk','lmnopqrstuv','wxyzABCDEFG'])]
  def read(url):
   if url==sources[0]['url']:raise ValueError('Нет субтитров')
   return {**PAGE,'url':url,'method':'video_transcript'}
  with patch('codi.learning.web_sources.channel_sources',return_value=sources),patch('codi.learning.web_sources.read_source',side_effect=read),patch('codi.learning.web_sources.search') as search:
   job=self.app.learning.start({'topic':'https://www.youtube.com/@sample','url':'https://www.youtube.com/@sample','minutes':1,'max_pages':1})
   job=self.finish(job['id']);self.assertEqual(job['saved'],1);self.assertEqual(job['sources'][0]['title'],'Lesson 1');search.assert_not_called()
   resumed=self.app.learning.resume(job['id']);job=self.finish(job['id']);self.assertEqual(job['saved'],2);self.assertEqual(len({r['url'] for r in job['sources']}),2)
 def test_delete_topic_removes_documents_memories_and_comparisons_with_backup(self):
  sources=[{'url':'https://one.example/a','title':'One'},{'url':'https://two.example/a','title':'Two'}]
  with patch('codi.learning.web_sources.search',return_value=sources),patch('codi.learning.web_sources.read_source',side_effect=lambda url:{**PAGE,'url':url}):
   job=self.app.learning.start({'topic':'Python','minutes':1,'max_pages':2});job=self.finish(job['id'])
  self.assertTrue(self.app.store.memories());self.assertTrue(self.app.knowledge.list())
  result=self.app.learning.delete(job['id']);self.assertTrue(Path(result['backup']).is_file())
  self.assertFalse(self.app.store.memories());self.assertFalse(self.app.knowledge.list());self.assertFalse(self.app.learning.jobs());self.assertFalse(self.app.knowledge.search('Python'))
  with self.app.store.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM chunk_search').fetchone()[0],0)
 def test_active_topic_cannot_be_deleted_while_it_is_saving(self):
  with patch('codi.learning.threading.Thread'):
   job=self.app.learning.start({'topic':'Python','minutes':1,'max_pages':1})
  with self.assertRaisesRegex(ValueError,'остановите'):self.app.learning.delete(job['id'])
  self.assertEqual(self.app.learning.get(job['id'])['id'],job['id'])
  self.app.learning.active.clear()
 def test_reference_install_is_idempotent_and_selective(self):
  library=self.app.engine.references
  with patch('codi.reference_library.REFERENCES',REFERENCES[:1]),patch('codi.reference_library.web_sources.read_source',return_value=PAGE):
   self.assertEqual(library.install(self.app.knowledge)['installed'],1);library.install(self.app.knowledge)
  self.assertEqual(len(self.app.knowledge.list()),1)
  self.assertFalse(library.find('привет'))
  self.assertEqual(len(library.find('Напиши Python функцию')),1)
  chat=self.app.store.create_chat('vibecoding');self.app.store.save_settings({**self.app.store.settings(),'rag_enabled':True});self.app.store.add_message(chat['id'],'user','Напиши Python функцию')
  messages,sources=self.app.engine.context(self.app.store.chat(chat['id']),self.app.store.settings());self.assertTrue(sources)
  self.app.knowledge.delete(sources[0]['document_id'])
  messages,sources=self.app.engine.context(self.app.store.chat(chat['id']),self.app.store.settings());self.assertFalse(sources)
 def test_svg_obj_validation_and_blend_is_binary(self):
  self.assertEqual(check_svg(SVG)['shapes'],1);self.assertEqual(check_obj(OBJ)['vertices'],3)
  for invalid in ['<svg/>','<svg><script>alert(1)</script></svg>','<svg><circle onclick="run()"/></svg>']:
   with self.assertRaises(ValueError):check_svg(invalid)
  with self.assertRaises(ValueError):check_obj(OBJ.replace('f 1 2 3','f 1 2 9'))
 def test_mesh_counts_and_closed_surface_are_checked_against_request(self):
  from codi.asset_checks import check_mesh_request
  with self.assertRaisesRegex(ValueError,'вершин'):check_mesh_request('6 вершин, 8 граней',OBJ)
  with self.assertRaisesRegex(ValueError,'замкнутой'):check_mesh_request('замкнутый объект',OBJ)
  octa='v 0 0 1\nv 0 0 -1\nv 1 0 0\nv 0 1 0\nv -1 0 0\nv 0 -1 0\nf 1 3 4\nf 1 4 5\nf 1 5 6\nf 1 6 3\nf 2 4 3\nf 2 5 4\nf 2 6 5\nf 2 3 6\n'
  self.assertTrue(check_mesh_request('замкнутый, 6 вершин, 8 треугольных граней',octa)['closed'])
 def test_artist_repairs_wrong_mesh_instead_of_claiming_success(self):
  workspace=self.root/'art';workspace.mkdir();self.app.store.save_settings({**self.app.store.settings(),'workspace':str(workspace),'tools_enabled':True,'project_autowrite':True})
  good='v 0 0 1\nv 0 0 -1\nv 1 0 0\nv 0 1 0\nv -1 0 0\nv 0 -1 0\nf 1 3 4\nf 1 4 5\nf 1 5 6\nf 1 6 3\nf 2 4 3\nf 2 5 4\nf 2 6 5\nf 2 3 6\n'
  calls=[]
  def stream(payload,op):
   calls.append(payload)
   yield {'message':{'tool_calls':[{'function':{'name':'propose_write','arguments':{'path':'model.obj','content':OBJ if len(calls)==1 else good}}}]},'done':True}
  self.app.llm.stream=stream;chat=self.app.store.create_chat('artist');self.app.store.add_message(chat['id'],'user','Создай model.obj: замкнутый, 6 вершин, 8 граней')
  events=list(self.app.engine.generate(chat['id'],self.app.engine.reserve(chat['id'])))
  self.assertEqual(events[-1]['status'],'complete');self.assertEqual(len(calls),2);self.assertEqual((workspace/'model.obj').read_text(encoding='utf-8'),good)
  self.assertTrue(any(e.get('status')=='error' and 'OBJ' in e.get('error','') for e in events))
 def test_short_asset_completion_does_not_skip_more_work(self):
  from codi.asset_checks import single_asset_request
  self.assertFalse(single_asset_request('Создай mascot.svg и объясни код',['D:/art/mascot.svg']))
  self.assertFalse(single_asset_request('Создай a.svg и b.obj',['D:/art/a.svg']))
  self.assertTrue(single_asset_request('Создай файл mascot.svg',['D:/art/mascot.svg']))
 def test_artist_writes_real_svg_and_obj_through_tools(self):
  workspace=self.root/'art';workspace.mkdir()
  self.app.store.save_settings({**self.app.store.settings(),'workspace':str(workspace),'tools_enabled':True,'project_autowrite':True})
  for filename,content in [('mascot.svg',SVG),('triangle.obj',OBJ)]:
   calls=[]
   def stream(payload,op):
    calls.append(payload)
    if len(calls)==1:yield {'message':{'tool_calls':[{'function':{'name':'propose_write','arguments':{'path':filename,'content':content}}}]},'done':True}
    else:yield {'message':{'content':'Файл создан.'},'done':True}
   self.app.llm.stream=stream;chat=self.app.store.create_chat('artist');self.app.store.add_message(chat['id'],'user','Создай файл '+filename)
   events=list(self.app.engine.generate(chat['id'],self.app.engine.reserve(chat['id'])))
   self.assertEqual(events[-1]['status'],'complete');self.assertEqual(len(calls),1);self.assertEqual((workspace/filename).read_text(encoding='utf-8'),content)
   result=self.app.tools.execute('project_check',{'path':filename},self.app.store.settings());self.assertFalse(result['executed'])

if __name__=='__main__':unittest.main()
