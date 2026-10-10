"""Structural checks for text art assets, without running supplied code."""
import math
import xml.etree.ElementTree as ET

def check_svg(text):
 if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():raise ValueError('SVG: объявления DTD и сущностей не поддерживаются')
 try:root=ET.fromstring(text)
 except ET.ParseError as exc:raise ValueError('SVG: некорректный XML: '+str(exc)) from exc
 if root.tag.rsplit('}',1)[-1]!='svg':raise ValueError('SVG: нужен корневой элемент svg')
 shapes=0
 for node in root.iter():
  tag=node.tag.rsplit('}',1)[-1]
  if tag.lower() in ('script','foreignobject'):raise ValueError('SVG-иллюстрация не должна содержать исполняемый код или HTML')
  if tag in ('path','circle','ellipse','rect','polygon','polyline','line','text','use'):shapes+=1
  for name,value in node.attrib.items():
   name=name.rsplit('}',1)[-1].lower()
   if name.startswith('on') or (name=='href' and value and not value.startswith('#')):raise ValueError('SVG: обработчики событий и внешние ссылки не поддерживаются')
 if not shapes:raise ValueError('SVG не содержит рисуемых элементов')
 return {'format':'svg','shapes':shapes,'visual_quality_verified':False}

def check_obj(text):
 counts={'v':0,'vt':0,'vn':0};faces=[];polygons=[]
 for line in text.splitlines():
  words=line.split('#',1)[0].split()
  if not words:continue
  kind=words[0]
  if kind in counts:
   minimum=2 if kind=='vt' else 3
   if len(words)-1<minimum:raise ValueError('OBJ: мало координат в '+kind)
   try:values=[float(v) for v in words[1:]]
   except ValueError:raise ValueError('OBJ: координаты должны быть числами') from None
   if not all(math.isfinite(v) for v in values):raise ValueError('OBJ: координаты должны быть конечными')
   counts[kind]+=1
  elif kind=='f':
   if len(words)<4:raise ValueError('OBJ: грани нужны минимум три вершины')
   polygon=[]
   for vertex in words[1:]:
    fields=vertex.split('/')
    if len(fields)>3 or not fields[0]:raise ValueError('OBJ: неверная ссылка на вершину')
    for field,group in zip(fields,('v','vt','vn')):
     if not field:continue
     try:index=int(field)
     except ValueError:raise ValueError('OBJ: индекс должен быть целым') from None
     if index==0 or (index<0 and -index>counts[group]):raise ValueError('OBJ: индекс вне массива '+group)
     faces.append((group,index))
     if group=='v':polygon.append(index if index>0 else counts['v']+index+1)
   if len(set(polygon))<3:raise ValueError('OBJ: вырожденная грань с повторением вершин')
   polygons.append(polygon)
 if counts['v']<3 or not faces:raise ValueError('OBJ: нужна сетка с вершинами и гранями')
 if any(index>counts[group] for group,index in faces):raise ValueError('OBJ: грань ссылается на отсутствующую вершину')
 from collections import Counter
 edges=Counter(tuple(sorted((face[i],face[(i+1)%len(face)]))) for face in polygons for i in range(len(face)))
 return {'format':'obj','vertices':counts['v'],'faces':len(polygons),'closed':bool(edges) and all(n==2 for n in edges.values()),'visual_quality_verified':False}


def single_asset_request(query,paths):
 """Finish only an explicit single SVG/OBJ creation, without further actions."""
 import re
 from pathlib import Path
 names=set(re.findall(r'(?<![\w.])([\w-]+\.(?:svg|obj))\b',query,re.I))
 if len(names)!=1 or len(paths)!=1:return False
 mentions=set(re.findall(r'(?<![\w.])([\w-]+\.[a-z][a-z0-9]{0,7})\b',query,re.I))
 if {v.casefold() for v in mentions}!={v.casefold() for v in names}:return False
 if re.search(r'папк|директори|тест|проверь|\b(?:и|а|затем|потом)\s+(?:сделай|создай|добавь|покажи|напиши|сохрани|подключи|сгенерируй)',query,re.I):return False
 if not re.search(r'создай|сделай|нарисуй',query,re.I):return False
 if re.search(r'объясни|открой|запусти|экспорт|рендер|анимац|переимен|удали|также|ещ[её] один|\.(?:py|html|js|mtl|gltf)\b',query,re.I):return False
 return Path(paths[0]).name.casefold()==next(iter(names)).casefold()


def check_mesh_request(query,text):
 import re
 report=check_obj(text);errors=[]
 for pattern,field,label in [(r'(\d+)\s+вершин','vertices','вершин'),(r'(\d+)\s+(?:треугольн\w*\s+)?гран','faces','граней')]:
  match=re.search(pattern,query,re.I)
  if match and report[field]!=int(match.group(1)):errors.append('требуется '+match.group(1)+' '+label+', получено '+str(report[field]))
 if re.search(r'замкнут|closed|watertight',query,re.I) and not report['closed']:errors.append('сетка должна быть замкнутой; есть открытые или неманифолдные рёбра')
 if errors:raise ValueError('OBJ не соответствует заданию: '+'; '.join(errors))
 return report
