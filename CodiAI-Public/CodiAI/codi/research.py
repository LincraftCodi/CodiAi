"""Bounded live research. Only the current question is sent to web search."""
import hashlib
import re
import time
from urllib.parse import urlsplit
from . import web_sources

def excerpt(text,query,limit=1600):
    words={w[:6] for w in re.findall(r'\w+',query.casefold()) if len(w)>3 and w not in {'расскажи','объясни','почему','какие','какой','пожалуйста','найди','интернете','сравни'}}
    blocks=[b.strip() for b in re.split(r'\n+',text) if b.strip()]
    ranked=sorted(range(len(blocks)),key=lambda i:sum(w in blocks[i].casefold() for w in words),reverse=True)
    selected=set(range(min(3,len(blocks))))
    size=sum(len(blocks[i]) for i in selected)
    for i in ranked:
        if i not in selected and size<limit:selected.add(i);size+=min(len(blocks[i]),700)
    return '\n'.join(blocks[i][:700] for i in sorted(selected))[:limit]

class Research:
    def __init__(self):self.cache={}
    def collect(self,query,operation,max_sources=8):
        if type(max_sources) is not int or max_sources not in (4,8,12):raise ValueError('Недопустимое число источников')
        query=query.strip()[:1000];key=(query.casefold(),max_sources);now=time.monotonic()
        cached=self.cache.get(key)
        if operation.cancelled.is_set():return
        if cached and now-cached[0]<300:
            yield {'type':'activity','text':'Поиск: использую прочитанные менее пяти минут назад источники…'}
            yield {'type':'research_result','value':cached[1]};return
        yield {'type':'activity','text':'Поиск: ищу источники в интернете…'}
        search_query=web_sources.search_topic(query)
        educational=bool(re.match(r'^(?:изучи|изучить|выучи|исследуй)\b',query,re.I))
        candidates=web_sources.search(search_query,min(24,max_sources*2),educational=educational)
        result={'sources':[],'error':'','requested':max_sources};hosts=set();errors=[];deadline=now+120
        # Four bounded network reads at once; model generation remains CPU-limited.
        from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
        pool=ThreadPoolExecutor(max_workers=4,thread_name_prefix='CodiRead')
        pending={};queued_hosts=set();remaining=iter(candidates)
        def fill():
            target=min(4,max_sources-len(result['sources']))
            while len(pending)<target:
                item=next(remaining,None)
                if item is None:break
                host=(urlsplit(item['url']).hostname or '').removeprefix('www.')
                if host in hosts or host in queued_hosts:continue
                queued_hosts.add(host);pending[pool.submit(web_sources.read_source,item['url'])]=host
        try:
            fill()
            while pending and len(result['sources'])<max_sources and time.monotonic()<deadline:
                if operation.cancelled.is_set():return
                done,_=wait(pending,timeout=.15,return_when=FIRST_COMPLETED)
                for future in done:
                    host=pending.pop(future);queued_hosts.discard(host)
                    yield {'type':'activity','text':'Поиск: читаю '+host+'…'}
                    try:
                        page=future.result();host=(urlsplit(page['url']).hostname or '').removeprefix('www.')
                        if host in hosts:continue
                        if operation.cancelled.is_set():return
                        material=excerpt(page['text'],query)
                        if len(material)<100:continue
                        result['sources'].append({'id':hashlib.sha256(page['url'].encode()).hexdigest()[:20],'name':page['title'],'url':page['url'],'position':0,'content':material})
                        hosts.add(host)
                    except (OSError,RuntimeError,ValueError) as exc:errors.append(str(exc)[:180])
                if not operation.cancelled.is_set():fill()
        finally:
            pool.shutdown(wait=False,cancel_futures=True)
        if not result['sources']:result['error']='Источники не удалось открыть. Поиск может быть недоступен; проверенный по интернету ответ сейчас не получен.'
        elif len(hosts)<2:result['error']='Открыт только один сайт: независимого сопоставления нет.'
        elif len(hosts)<max_sources:result['error']='Прочитано '+str(len(hosts))+' из '+str(max_sources)+' запрошенных сайтов; остальные недоступны или время чтения закончилось.'
        if result['sources']:
            if len(self.cache)>=24:self.cache.pop(next(iter(self.cache)))
            self.cache[key]=(time.monotonic(),result)
        yield {'type':'research_result','value':result}
