import threading,unittest
from unittest.mock import patch
from tests import test_learning_memory as fixtures
from codi.learning import Learning
from server import make_server
from widget import Client

class LearningResumeTests(unittest.TestCase):
 setUp=fixtures.LearningMemoryTests.setUp
 tearDown=fixtures.LearningMemoryTests.tearDown
 finish=fixtures.LearningMemoryTests.finish

 def seed(self,ident='resume',saved=1,target=2,status='stopped'):
  with self.app.store.db() as db:db.execute('INSERT INTO learning_jobs VALUES(?,?,?,?,?,?,?,?,?)',(ident,'Математика',status,'Остановлено',1,target,1,1,''))
  for n in range(saved):self.app.learning.save(ident,'Математика',{**fixtures.PAGE,'url':'https://example.org/old'+str(n)},'Старый конспект')
  return ident

 def test_resume_http_preserves_saved_pages_and_reads_checkpoint_first(self):
  ident=self.seed();new={**fixtures.PAGE,'url':'https://example.org/new'}
  self.app.learning.checkpoint(ident,'',[{'url':new['url'],'title':'Очередь'}])
  self.app.learning=Learning(self.app.store,self.app.llm,self.app.knowledge,self.app.engine)
  server=make_server(0,self.app);threading.Thread(target=server.serve_forever,daemon=True).start()
  try:
   with patch('codi.learning.web_sources.search',return_value=[{'url':'https://example.org/old0','title':'Старое'}]),patch('codi.learning.web_sources.read_source',return_value=new) as read,patch.object(self.app.learning,'summarize',return_value='Новый конспект'),patch.object(self.app.learning,'compare'):
    client=Client('http://127.0.0.1:'+str(server.server_port));client.request('/api/learn/resume',{'id':ident});job=self.finish(ident)
   read.assert_called_once_with(new['url']);self.assertEqual(job['saved'],2);self.assertEqual(job['progress_percent'],100);self.assertEqual(job['sources'][0]['summary'],'Старый конспект')
  finally:server.shutdown();server.server_close()

 def test_cancelled_current_page_remains_pending_after_restart(self):
  ident=self.seed(saved=0);new={**fixtures.PAGE,'url':'https://example.org/new'}
  self.app.learning.checkpoint(ident,'',[{'url':new['url'],'title':'Новая'}]);cancel=threading.Event()
  def summarize(*args):cancel.set();return None
  with patch('codi.learning.web_sources.search',return_value=[]),patch('codi.learning.web_sources.read_source',return_value=new),patch.object(self.app.learning,'summarize',side_effect=summarize):self.app.learning.run(ident,'Математика','',None,1,2,cancel)
  self.assertEqual(self.app.learning.get(ident)['saved'],0)
  self.app.learning=Learning(self.app.store,self.app.llm,self.app.knowledge,self.app.engine)
  with patch('codi.learning.web_sources.search',return_value=[]),patch('codi.learning.web_sources.read_source',return_value=new) as read,patch.object(self.app.learning,'summarize',return_value='Текст'):
   self.app.learning.resume(ident);job=self.finish(ident)
  read.assert_called_once_with(new['url']);self.assertEqual(job['saved'],1);self.assertEqual(job['progress_percent'],50)

 def test_completed_topic_extends_plan_even_after_many_saved_pages(self):
  ident=self.seed(saved=13,target=13,status='completed');new={**fixtures.PAGE,'url':'https://example.org/new'}
  with patch('codi.learning.web_sources.search',return_value=[{'url':new['url'],'title':'Новое'}]),patch('codi.learning.web_sources.read_source',return_value=new) as read,patch.object(self.app.learning,'summarize',return_value='Текст'),patch.object(self.app.learning,'compare'):
   self.app.learning.resume(ident);job=self.finish(ident)
  read.assert_called_once();self.assertEqual(job['max_pages'],17);self.assertEqual(job['saved'],14)

 def test_unknown_and_concurrent_resume_do_not_change_saved_plan(self):
  ident=self.seed()
  with self.assertRaises(ValueError):self.app.learning.resume('missing')
  self.app.learning.active['other']=threading.Event()
  try:
   with self.assertRaises(ValueError):self.app.learning.resume(ident)
   self.assertEqual(self.app.learning.get(ident)['status'],'stopped')
  finally:self.app.learning.active.clear()

if __name__=='__main__':unittest.main()
