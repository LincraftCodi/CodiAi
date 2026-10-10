"""Public-page reader with bounded responses and validated, pinned connections."""
import http.client
import json
import ipaddress
import re
import socket
import ssl
from urllib.parse import urlsplit,urlunsplit,urljoin,quote,parse_qs
from bs4 import BeautifulSoup

MAX_BODY=2_000_000
def public_url(value,resolve=True):
    if not isinstance(value,str) or len(value)>3000:raise ValueError('Ссылка слишком длинная')
    parts=urlsplit(value.strip())
    if parts.scheme not in ('http','https') or not parts.hostname or parts.username or parts.password or parts.port not in (None,80,443):
        raise ValueError('Нужна публичная ссылка http:// или https:// без пароля')
    host=parts.hostname.encode('idna').decode('ascii')
    if host.lower() in ('localhost','localhost.localdomain') or host.lower().endswith(('.localhost','.local')):raise ValueError('Локальные адреса не используются для изучения сайтов')
    if resolve:
        addresses=list(dict.fromkeys(r[4][0] for r in socket.getaddrinfo(host,parts.port or (443 if parts.scheme=='https' else 80),type=socket.SOCK_STREAM)))
        if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):raise ValueError('Ссылка должна вести на публичный сайт, а не локальный адрес')
    else:
        try:address=ipaddress.ip_address(host)
        except ValueError:address=None
        if address is not None and not address.is_global:raise ValueError('Нужен публичный сайт')
        addresses=[]
    authority=host if ':' not in host else '['+host+']'
    if parts.port:authority+=':'+str(parts.port)
    canonical=urlunsplit((parts.scheme,authority,quote(parts.path or '/',safe="/%:@!$&'()*+,;=-._~"),quote(parts.query,safe="%=&/:?@!$'()*+,;-._~"),''))
    return canonical,addresses

def fetch(value):
    for hop in range(6):
        url,addresses=public_url(value);parts=urlsplit(url);port=parts.port or (443 if parts.scheme=='https' else 80)
        connection=http.client.HTTPSConnection(parts.hostname,port,timeout=15,context=ssl.create_default_context()) if parts.scheme=='https' else http.client.HTTPConnection(parts.hostname,port,timeout=15)
        connection._create_connection=lambda address,timeout,source_address=None:socket.create_connection((addresses[0],port),timeout)
        try:
            connection.request('GET',parts.path+('?' +parts.query if parts.query else ''),headers={'User-Agent':'CodiAI/0.4 (educational reader)','Accept':'text/html,text/plain,application/json,text/vtt;q=0.9','Accept-Encoding':'identity'})
            response=connection.getresponse()
            if response.status in (301,302,303,307,308):
                location=response.getheader('Location')
                if not location:raise ValueError('Сайт вернул пустое перенаправление')
                value=urljoin(url,location);continue
            if response.status!=200:raise ValueError('Сайт не открылся: HTTP '+str(response.status))
            kind=response.getheader('Content-Type','text/html')
            if not any(t in kind.lower() for t in ('text/','application/xhtml','application/json','application/xml')):raise ValueError('Нужна текстовая страница или субтитры. Этот тип файла пока не поддерживается')
            raw=response.read(MAX_BODY+1)
            if len(raw)>MAX_BODY:raise ValueError('Страница слишком большая для чтения')
            match=re.search(r'charset=([^;\s]+)',kind,re.I);encoding=match.group(1).strip('"') if match else None
            if encoding:
                try:text=raw.decode(encoding,errors='replace')
                except LookupError:text=raw.decode('utf-8',errors='replace')
            else:
                text=BeautifulSoup(raw,'html.parser').decode() if 'html' in kind.lower() else raw.decode('utf-8',errors='replace')
            return url,text,kind
        finally:connection.close()
    raise ValueError('Слишком много перенаправлений')

def extract(url,html,kind='text/html'):
    if 'html' not in kind.lower():return {'url':url,'title':urlsplit(url).hostname,'text':html[:60000],'links':[],'method':'text'}
    soup=BeautifulSoup(html,'html.parser');title=soup.title.get_text(' ',strip=True)[:240] if soup.title else urlsplit(url).hostname
    for node in soup.select('script,style,noscript,nav,header,footer,form,button,iframe,aside'):node.decompose()
    content=soup.select_one('.mw-parser-output') or soup.select_one('.body[role=main]') or soup.select_one('#mainContent') or soup.find('article') or soup.find('main') or soup.find(id='mw-content-text') or soup.body or soup
    for math in content.find_all('math'):
        annotation=math.find('annotation',attrs={'encoding':'application/x-tex'})
        formula=math.get('alttext') or (annotation.get_text() if annotation else None)
        if formula:math.replace_with(' '+formula+' ')
    # Preserve code blocks as single text nodes, including indentation/newlines.
    for pre in content.find_all('pre'):
        pre.replace_with('\n'+pre.get_text('',strip=False)+'\n')
    links=[]
    for a in content.find_all('a',href=True):
        href=urljoin(url,a['href'])
        try:target,_=public_url(href,resolve=False)
        except ValueError:continue
        if target!=url and not any(l['url']==target for l in links):links.append({'url':target,'title':a.get_text(' ',strip=True)[:160]})
        if len(links)>=80:break
    text=content.get_text('\n',strip=True);text=re.sub(r'\n{3,}','\n\n',text)
    if len(text.strip())<100:raise ValueError('На странице мало читаемого текста. Откройте оригинал в браузере и нажмите «Изучить страницу»')
    return {'url':url,'title':title or url,'text':text[:60000],'links':links,'method':'web_text'}

def video_id(value):
    parts=urlsplit(value);host=(parts.hostname or '').lower()
    if host in ('youtu.be','www.youtu.be'):ident=parts.path.strip('/').split('/')[0]
    elif host in ('youtube.com','www.youtube.com','m.youtube.com'):
        ident=parse_qs(parts.query).get('v',[''])[0] if parts.path=='/watch' else parts.path.strip('/').split('/')[-1] if parts.path.startswith(('/shorts/','/embed/','/live/')) else ''
    else:return None
    if not ident and youtube_collection(value):return None
    if not re.fullmatch(r'[\w-]{11}',ident):raise ValueError('Нужна ссылка на конкретное видео YouTube')
    return ident

def read_source(value):
    url,_=public_url(value)
    if youtube_collection(url):
        links=channel_sources(url)
        return {'url':url,'title':'Канал / плейлист YouTube','text':'Список доступных роликов. Сами видео ещё не изучены; добавьте канал в память, чтобы прочитать доступные субтитры.\n\n'+'\n'.join(r['title']+' — '+r['url'] for r in links),'links':links,'method':'youtube_collection'}
    ident=video_id(url)
    if ident:
        from youtube_transcript_api import YouTubeTranscriptApi
        import requests
        class BoundedSession(requests.Session):
            def request(self,*args,**kwargs):kwargs.setdefault('timeout',15);return super().request(*args,**kwargs)
        try:
            with BoundedSession() as session:
                api=YouTubeTranscriptApi(http_client=session);tracks=api.list(ident)
                try:track=tracks.find_transcript(['ru','en'])
                except Exception:track=next(iter(tracks))
                result=track.fetch();text='\n'.join(f'[{int(s.start)//60:02d}:{int(s.start)%60:02d}] {s.text}' for s in result)
                if not text.strip():raise ValueError('Пустые субтитры')
                return {'url':url,'title':'Видео YouTube '+ident,'text':text[:60000],'links':[],'method':'video_transcript','language':result.language_code}
        except Exception as exc:raise ValueError('Не удалось получить субтитры видео. Оно может быть недоступно, заблокировано или без расшифровки. Можно загрузить текст субтитров в «Знания». Видео без субтитров пока не разбирается.') from exc
    url,html,kind=fetch(url)
    return extract(url,html,kind)

def search_topic(value):
    # Preserve phrases and conjunctions: never search individual words separately.
    value=re.sub(r'\s+',' ',value.strip())
    return re.sub(r'^(?:(?:пожалуйста[, ]+)?(?:изучи|изучить|выучи|исследуй|найди информацию (?:о|про)|расскажи (?:о|про)|объясни))\s+','',value,flags=re.I).strip()


def study_guides(topic):
    low=topic.casefold();guides=[]
    general=bool(re.search(r'язык\w* программ|programming languages',low))
    specs=[(general or 'python' in low or 'питон' in low,'https://docs.python.org/3/tutorial/introduction.html','The Python Tutorial'),
           (general or 'javascript' in low or 'скрипт' in low,'https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Grammar_and_types','JavaScript Guide — MDN'),
           (general or 'powershell' in low,'https://learn.microsoft.com/en-us/powershell/scripting/overview','PowerShell scripting overview'),
           ('bash' in low,'https://www.gnu.org/software/bash/manual/bash.html','GNU Bash manual')]
    for enabled,url,title in specs:
        if enabled:guides.append({'url':url,'title':title,'snippet':'Официальное руководство','kind':'guide'})
    return guides


def youtube_collection(value):
    parts=urlsplit(value);host=(parts.hostname or '').lower()
    if host not in ('youtube.com','www.youtube.com','m.youtube.com'):return None
    path=parts.path.rstrip('/')
    if path=='/playlist':
        ident=parse_qs(parts.query).get('list',[''])[0]
        if not re.fullmatch(r'[\w-]{10,100}',ident):raise ValueError('Некорректная ссылка на плейлист YouTube')
        return 'https://www.youtube.com/playlist?list='+ident
    if path.startswith('/@') or re.match(r'^/(?:channel|c|user)/[^/]+',path):
        segments=path.split('/')
        root='/'+segments[1] if path.startswith('/@') else '/'+segments[1]+'/'+segments[2]
        return 'https://www.youtube.com'+root+'/videos'
    return None


def youtube_page_videos(html,limit=24):
    marker=re.search(r'(?:var\s+ytInitialData|window\["ytInitialData"\]|ytInitialData)\s*=\s*',html)
    if not marker:return []
    data,_=json.JSONDecoder().raw_decode(html[marker.end():]);stack=[data];rows=[];seen=set();nodes=0
    while stack and len(rows)<limit and nodes<60000:
        node=stack.pop();nodes+=1
        if isinstance(node,dict):
            video=node.get('videoRenderer') or node.get('playlistVideoRenderer')
            lockup=node.get('lockupViewModel')
            ident='';title='';duration=''
            if video:
                ident=video.get('videoId','');title=''.join(r.get('text','') for r in video.get('title',{}).get('runs',[])) or video.get('title',{}).get('simpleText','')
                duration=video.get('lengthText',{}).get('simpleText','')
            elif lockup and lockup.get('contentType')=='LOCKUP_CONTENT_TYPE_VIDEO':
                ident=lockup.get('contentId','');title=lockup.get('metadata',{}).get('lockupMetadataViewModel',{}).get('title',{}).get('content','')
            if re.fullmatch(r'[\w-]{11}',ident) and ident not in seen:
                rows.append({'content':'https://www.youtube.com/watch?v='+ident,'title':title or ident,'duration':duration});seen.add(ident)
            stack.extend(reversed(list(node.values())))
        elif isinstance(node,list):stack.extend(reversed(node))
    return rows


def youtube_results(topic,limit=4):
    _,html,_=fetch('https://www.youtube.com/results?search_query='+quote(topic+' урок'))
    return youtube_page_videos(html,limit)


def channel_sources(value,limit=24):
    target=youtube_collection(value)
    if not target:raise ValueError('Нужна ссылка на канал или плейлист YouTube')
    _,html,_=fetch(target)
    rows=youtube_page_videos(html,min(80,limit))
    if not rows:raise ValueError('Не удалось получить список роликов канала. Канал может быть закрыт, пуст или недоступен. Попробуйте ссылку на конкретный ролик.')
    return [{'url':r['content'],'title':r['title'],'kind':'video'} for r in rows]


def search(topic,limit=6,educational=True):
    from ddgs import DDGS
    from concurrent.futures import ThreadPoolExecutor
    topic=search_topic(topic)[:1000]
    if not topic:return []
    limit=max(1,min(24,limit));count=max(6,limit)
    def text_query(query):
        # auto includes Wikipedia's word lookup, which is not a web search.
        for backend in ('bing,brave,duckduckgo','yandex,yahoo'):
            try:
                rows=DDGS(timeout=8).text(query,max_results=count,safesearch='off',backend=backend,region='ru-ru')
                if rows:return rows
            except Exception:continue
        return []
    def usable_videos(rows):
        valid=[]
        for row in rows:
            try:
                if not video_id(row.get('content','')):continue
            except (ValueError,TypeError):continue
            duration=str(row.get('duration','')).split(':')
            if len(duration)==2 and all(p.isdigit() for p in duration) and int(duration[0])*60+int(duration[1])<60:continue
            valid.append(row)
        return valid
    def videos():
        try:
            rows=usable_videos(DDGS(timeout=8).videos(topic+' обучение',max_results=6,safesearch='off'))
            if rows:return rows
        except Exception:pass
        # Some video search endpoints are blocked; use a whole-topic web query.
        rows=usable_videos([{**r,'content':r.get('href',''),'description':r.get('body','')} for r in text_query(topic+' урок site:youtube.com/watch')])
        if rows:return rows
        try:return youtube_results(topic,6)
        except (OSError,ValueError):return []
    queries=[topic,topic+(' руководство примеры учебник' if educational else ' источники объяснение')]
    with ThreadPoolExecutor(max_workers=3,thread_name_prefix='CodiSearch') as pool:
        futures=[pool.submit(text_query,q) for q in queries]
        video=pool.submit(videos) if educational or re.search(r'видео|ролик|video',topic,re.I) else None
        groups=[future.result() for future in futures]
        video_rows=video.result() if video else []
    results=[]
    for rows in groups:
        for row in rows:
            try:url,_=public_url(row.get('href',''),resolve=False)
            except (ValueError,TypeError):continue
            results.append({'url':url,'title':str(row.get('title',url))[:240],'snippet':str(row.get('body',''))[:700],'kind':'web'})
    clips=[]
    for row in video_rows:
        try:
            url,_=public_url(row.get('content',''),resolve=False)
            if not video_id(url):continue
        except (ValueError,TypeError):continue
        # Skip very short promotional clips; longer lessons still need captions.
        duration=str(row.get('duration','')).split(':')
        if len(duration)==2 and all(p.isdigit() for p in duration) and int(duration[0])*60+int(duration[1])<60:continue
        clips.append({'url':url,'title':str(row.get('title',url))[:240],'snippet':str(row.get('description',''))[:700],'kind':'video'})
    guides=study_guides(topic) if educational else []
    # Read primary guides first, then give a video a chance before more web pages.
    results=guides+clips[:1]+results+clips[1:]
    unique=list({r['url']:r for r in results}.values());first=[];rest=[];hosts=set()
    for item in unique:
        host=(urlsplit(item['url']).hostname or '').removeprefix('www.')
        if host in hosts:rest.append(item)
        else:first.append(item);hosts.add(host)
    return (first+rest)[:limit]
