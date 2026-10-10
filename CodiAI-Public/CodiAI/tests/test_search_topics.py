import threading,time,unittest
from unittest.mock import patch
from codi import web_sources
from codi.research import Research
from codi.engine import Operation

class SearchTopicTests(unittest.TestCase):
 def test_whole_topic_primary_guides_video_and_explicit_web_engines(self):
  calls=[]
  class Search:
   def __init__(self,**kw):pass
   def text(self,q,**kw):
    calls.append((q,kw))
    return [{'href':'https://lessons.example/a','title':'Programming and scripting','body':'A lesson'}]
   def videos(self,q,**kw):return [{'content':'https://www.youtube.com/watch?v=abcdefghijk','title':'Full course','duration':'30:00'}]
  with patch('ddgs.DDGS',Search):rows=web_sources.search('изучи языки программирования и скрипты',12)
  self.assertTrue(all('языки программирования и скрипты' in q for q,_ in calls))
  self.assertTrue(all(kw['backend']!='auto' and 'wikipedia' not in kw['backend'] for _,kw in calls))
  self.assertTrue(any(r['kind']=='video' for r in rows))
  self.assertTrue(any('docs.python.org' in r['url'] for r in rows))
  self.assertTrue(any('learn.microsoft.com' in r['url'] for r in rows))
 def test_failed_search_does_not_invent_wikipedia_url(self):
  with patch('ddgs.DDGS',side_effect=RuntimeError('offline')),patch('codi.web_sources.youtube_results',return_value=[]):
   self.assertEqual(web_sources.search('неизвестная составная тема'),[])
 def test_video_endpoint_failure_falls_back_to_topic_video_query(self):
  calls=[]
  class Search:
   def __init__(self,**kw):pass
   def text(self,q,**kw):
    calls.append(q)
    return [{'href':'https://www.youtube.com/watch?v=abcdefghijk','title':'Course'}] if 'site:youtube.com' in q else []
   def videos(self,*a,**kw):raise RuntimeError('blocked')
  with patch('ddgs.DDGS',Search):rows=web_sources.search('изучи линейные уравнения',6)
  self.assertEqual(rows[0]['kind'],'video');self.assertIn('линейные уравнения урок site:youtube.com/watch',calls)
 def test_public_youtube_fallback_extracts_real_video_links(self):
  import json
  payload={'contents':[{'videoRenderer':{'videoId':'abcdefghijk','title':{'runs':[{'text':'Programming course'}]},'lengthText':{'simpleText':'45:00'}}}]}
  html='var ytInitialData = '+json.dumps(payload)+';'
  with patch('codi.web_sources.fetch',return_value=('https://www.youtube.com/results',html,'text/html')):
   rows=web_sources.youtube_results('programming languages')
  self.assertEqual(rows[0]['content'],'https://www.youtube.com/watch?v=abcdefghijk')
  self.assertEqual(rows[0]['duration'],'45:00')
 def test_programming_pages_preserve_code_and_remove_sphinx_navigation(self):
  html='<title>Python</title><div>Navigation SHOULD NOT BE READ</div><div class="body" role="main"><p>'+('A Python introduction. '*10)+'</p><pre><span>spam</span> = <span>1</span>\nif spam:\n    print(spam)\n</pre></div>'
  page=web_sources.extract('https://docs.python.org/3/tutorial/introduction.html',html)
  self.assertNotIn('SHOULD NOT BE READ',page['text'])
  self.assertIn('spam = 1\nif spam:\n    print(spam)',page['text'])
 def test_reads_overlap_instead_of_waiting_for_each_site(self):
  active=0;peak=0;lock=threading.Lock()
  candidates=[{'url':'https://site'+str(n)+'.org/a'} for n in range(4)]
  def read(url):
   nonlocal active,peak
   with lock:active+=1;peak=max(peak,active)
   time.sleep(.05)
   with lock:active-=1
   return {'url':url,'title':'Lesson','text':'Linear equations and algebra. '*40}
  with patch('codi.research.web_sources.search',return_value=candidates),patch('codi.research.web_sources.read_source',side_effect=read):
   result=list(Research().collect('изучи линейные уравнения',Operation(),4))[-1]['value']
  self.assertEqual(len(result['sources']),4);self.assertGreater(peak,1)

if __name__=='__main__':unittest.main()
