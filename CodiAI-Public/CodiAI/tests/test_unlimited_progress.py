import unittest
from unittest.mock import patch
from tests import test_super_and_widget_actions as fixtures
from codi.learning import Learning

class UnlimitedProgressTests(unittest.TestCase):
 setUp=fixtures.SuperAndWidgetTests.setUp
 tearDown=fixtures.SuperAndWidgetTests.tearDown

 def test_length_cap_continues_same_answer_past_old_time_limit(self):
  calls=[]
  def stream(payload,op):
   calls.append(payload)
   yield {'message':{'content':'Начало ' if len(calls)==1 else 'конец.'},'done':True,'done_reason':'length' if len(calls)==1 else 'stop'}
  self.app.llm.stream=stream
  chat=self.app.store.create_chat('general');self.app.store.add_message(chat['id'],'user','Длинный ответ')
  # Simulate > five minutes without waiting or depending on the CPU speed.
  with patch('codi.engine.time.monotonic',side_effect=[0,700]):
   events=list(self.app.engine.generate(chat['id'],self.app.engine.reserve(chat['id'])))
  self.assertEqual(events[-1]['status'],'complete');self.assertEqual(len(calls),2)
  self.assertTrue(all(p['options']['num_predict']==-1 for p in calls))
  answer=self.app.store.chat(chat['id'])['messages'][-1]
  self.assertEqual(answer['content'],'Начало конец.');self.assertEqual(answer['metadata']['duration_seconds'],700)

 def test_stop_still_cancels_continuation(self):
  chat=self.app.store.create_chat('general');self.app.store.add_message(chat['id'],'user','Продолжай')
  op=self.app.engine.reserve(chat['id'])
  def stream(payload,operation):
   yield {'message':{'content':'Часть'},'done':True,'done_reason':'length'}
   operation.cancel()
  self.app.llm.stream=stream
  events=list(self.app.engine.generate(chat['id'],op))
  self.assertEqual(events[-1]['status'],'stopped');self.assertFalse(self.app.engine.active)

 def test_percent_tracks_saved_plan_and_survives_reload(self):
  for status,saved,expected in [('queued',0,0),('running',3,50),('running',6,99),('completed',6,100),('partial',2,33),('interrupted',3,50),('stopped',3,50)]:
   job=Learning.with_progress({'status':status,'saved':saved,'max_pages':6})
   self.assertEqual(job['progress_percent'],expected)
  with self.app.store.db() as db:
   db.execute('INSERT INTO learning_jobs VALUES(?,?,?,?,?,?,?,?,?)',('progress-test','Test','running','Reading',3,6,1,1,''))
   for n in range(3):db.execute('INSERT INTO learning_sources VALUES(?,?,?,?,?,?,?,?,?)',(str(n),'progress-test','https://example.org/'+str(n),'Test','Text','web_text',None,None,1))
  self.assertEqual(self.app.learning.get('progress-test')['progress_percent'],50)
  restored=Learning(self.app.store,self.app.llm,self.app.knowledge,self.app.engine)
  self.assertEqual(restored.jobs()[0]['progress_percent'],50)
  self.assertEqual(restored.jobs()[0]['status'],'interrupted')

if __name__=='__main__':unittest.main()
