"""Offline primary references: selective retrieval, not training model weights."""
import json,re,hashlib,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from .research import excerpt
from . import web_sources

REFERENCES=[
 ('python',r'python|питон|пайтон|\.py\b','Python: функции, скрипты','https://docs.python.org/3/tutorial/controlflow.html'),
 ('javascript',r'javascript|джаваскрипт|\bjs\b|\.js\b','JavaScript: грамматика и типы','https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Grammar_and_types'),
 ('typescript',r'typescript|тайпскрипт|\bts\b|\.tsx?\b','TypeScript: типы и функции','https://www.typescriptlang.org/docs/handbook/2/everyday-types.html'),
 ('powershell',r'powershell|пауэршелл|\.ps1\b','PowerShell: скрипты и параметры','https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_scripts'),
 ('bash',r'\bbash\b|shell|\.sh\b','Bash: скрипты и кавычки','https://www.gnu.org/software/bash/manual/html_node/Shell-Scripts.html'),
 ('rust',r'\brust\b|раст|\.rs\b','Rust: функции и типы','https://doc.rust-lang.org/book/ch03-03-how-functions-work.html'),
 ('go',r'\bgo\b|golang|\.go\b','Go: пакеты и обработка ошибок','https://go.dev/doc/tutorial/handle-errors'),
 ('csharp',r'c#|csharp|си[ -]?шарп|\.cs\b','C#: основы языка','https://learn.microsoft.com/en-us/dotnet/csharp/tour-of-csharp/'),
 ('cpp',r'c\+\+|cpp|си[ -]?плюс|\.cpp\b','C++: функции и объявления','https://learn.microsoft.com/en-us/cpp/cpp/functions-cpp'),
 ('java',r'\bjava\b|джава|джава|\.java\b','Java: основы языка (Java SE 8 Tutorial)','https://docs.oracle.com/javase/tutorial/java/nutsandbolts/'),
 ('lua',r'\blua\b|луа|\.lua\b','Lua: функции и области видимости','https://www.lua.org/pil/5.html'),
 ('luau',r'\bluau\b|роблокс|roblox|\.luau\b','Luau: синтаксис скриптов Roblox','https://luau.org/syntax'),
 ('blender',r'blender|блендер|3d|3д|тр[её]хмер|меш|полигон|\.obj\b','Blender: создание геометрии Mesh','https://docs.blender.org/api/current/bpy.types.Mesh.html'),
 ('blender-materials',r'blender|блендер|3d|3д|тр[её]хмер|материал|освещен','Blender: материалы и ноды','https://docs.blender.org/api/current/bpy.types.Material.html'),
 ('svg',r'\bsvg\b|рисунок|нарисуй|персонаж|маскот|иллюстрац|аватар|иконк','SVG: рисование персонажей и контуров','https://developer.mozilla.org/en-US/docs/Web/SVG/Tutorials/SVG_from_scratch/Paths'),
]

class ReferenceLibrary:
 def __init__(self,directory):
  self.directory=Path(directory);self.stamp=None;self.entries=[];self.cache={}
 def find(self,query,mode='general'):
  manifest=self.directory/'index.json'
  try:stamp=manifest.stat().st_mtime_ns
  except OSError:return []
  if stamp!=self.stamp:
   try:self.entries=json.loads(manifest.read_text(encoding='utf-8'))
   except (OSError,ValueError):return []
   self.stamp=stamp;self.cache.clear()
  key=(query.casefold()[:2000],mode)
  if key in self.cache:return [dict(r) for r in self.cache[key]]
  selected=[spec for spec in REFERENCES if re.search(spec[1],key[0],re.I)]
  if mode=='artist' and not selected:selected=[REFERENCES[-3],REFERENCES[-1]]
  # Two specific references at most. A greeting never loads the whole library.
  result=[]
  for ident,pattern,name,url in selected[:2]:
   entry=next((e for e in self.entries if e['key']==ident),None)
   if not entry:continue
   try:page=json.loads((self.directory/(ident+'.json')).read_text(encoding='utf-8'))
   except (OSError,ValueError):continue
   terms=query+' '+ident+' function example mesh from_pydata material nodes path'
   text=excerpt(page['text'],terms,1400)
   result.append({'id':'reference-'+ident,'document_id':entry.get('document_id'),'name':name,'url':page['url'],'position':0,'content':text})
  if len(self.cache)>=64:self.cache.pop(next(iter(self.cache)))
  self.cache[key]=result
  return [dict(r) for r in result]

 def install(self,knowledge):
  self.directory.mkdir(parents=True,exist_ok=True)
  try:old=json.loads((self.directory/'index.json').read_text(encoding='utf-8'))
  except (OSError,ValueError):old=[]
  def load(spec):
   ident,pattern,name,url=spec
   try:
    page=web_sources.read_source(url)
    path=self.directory/(ident+'.json');temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(page,ensure_ascii=False),encoding='utf-8');temporary.replace(path)
    return spec,page,None
   except Exception as exc:return spec,None,str(exc)
  entries=[];errors=[]
  existing={d['id'] for d in knowledge.list()}
  with ThreadPoolExecutor(max_workers=4,thread_name_prefix='CodiLibrary') as pool:
   for spec,page,error in pool.map(load,REFERENCES):
    ident,pattern,name,url=spec
    previous=next((e for e in old if e['key']==ident),None)
    if error:
     errors.append({'key':ident,'error':error})
     if previous:entries.append(previous)
     continue
    checksum=hashlib.sha256(page['text'].encode()).hexdigest()
    if previous and previous.get('sha256')==checksum and previous.get('document_id') in existing:
     entries.append(previous);continue
    document=knowledge.add('Справочник Codi · '+name,'Источник: '+page['url']+'\nТема: '+name+'\n\n'+page['text'],semantic=False)
    if previous and previous.get('document_id') in existing:knowledge.delete(previous['document_id'])
    entries.append({'key':ident,'name':name,'url':page['url'],'sha256':checksum,'document_id':document['id'],'updated':time.time()})
  path=self.directory/'index.json';temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)
  return {'installed':len(entries),'errors':errors,'directory':str(self.directory)}
