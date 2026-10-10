"""Deterministic names and destinations for natural-language create commands."""
import re
from pathlib import Path

QUOTES=re.compile(r'"[^"\n]*"|«[^»\n]*»|\x27[^\x27\n]*\x27')

def strip_name(value):
 value=value.strip().lstrip(':：').strip()
 if len(value)>=2 and (value[0],value[-1]) in (('"','"'),('«','»'),("'","'")):
  return value[1:-1].strip()
 label=r'(?:с\s+(?:названием|назанием|названем|названи[её]м|нащзванием|именем)|под\s+(?:названием|именем)|название|названием|имя|(?:которая|который)\s+называется|назови(?:\s+(?:её|ее|его))?|названную|названный|с\s+названи[её]м)'
 for _ in range(3):
  updated=re.sub(r'^(?:мне\s+)?'+label+r'(?:\s*[:：]\s*|\s+)', '',value,flags=re.I).strip()
  if updated==value:break
  value=updated
 if len(value)>=2 and (value[0],value[-1]) in (('"','"'),('«','»'),("'","'")):return value[1:-1].strip()
 return value.strip('«»"\x27 ').rstrip('!.').strip()

CONTENT=re.compile(r'\s+(?:с текстом|с содержимым|с содержанием|с кодом)\s*[:：]?\s*',re.I)

def command_mask(value):
 mask=list(value)
 for match in QUOTES.finditer(value):mask[match.start():match.end()]='X'*len(match.group())
 masked=''.join(mask)
 content=CONTENT.search(masked)
 if content:masked=masked[:content.start()]+' '*len(masked[content.start():])
 if re.match(r'^(?:запиши|напиши)\s+в\s+(?:этот файл|этот документ)\b',value,re.I):return ' '*len(value)
 return masked

def split_commands(value):
 if not re.match(r'^(?:открой|запусти|создай|сделай|переименуй)\b',value,re.I):return [value]
 pattern=r'\s+(?:и(?:\s+потом)?|затем|потом)\s+(?=(?:открой|запусти|создай|сделай|переименуй)\b)'
 matches=list(re.finditer(pattern,command_mask(value),re.I))
 result=[];start=0
 for match in matches:result.append(value[start:match.start()]);start=match.end()
 result.append(value[start:]);return result

def extract_location(value):
 masked=command_mask(value)
 pattern=re.compile(r'\b(?:на рабочем столе|в (?:этой|выбранной|текущей) папке|в папке проекта|здесь)\b',re.I)
 matches=list(pattern.finditer(masked));desktop=any(m.group().casefold()=='на рабочем столе' for m in matches)
 for match in reversed(matches):value=value[:match.start()]+' '+value[match.end():]
 return value.strip(),desktop

def parse_create(value):
 match=re.fullmatch(r'(?:создай|сделай|создайте)(?:\s+мне)?\s+(.+)',value,re.I|re.S)
 if not match:return None
 body,desktop=extract_location(match[1])
 match=re.fullmatch(r'(?:новую\s+)?(?:папку|каталог)\s*[:：]?\s*(.*)',body,re.I|re.S)
 if match:return {'kind':'folder','name':strip_name(match[1]),'desktop':desktop}
 match=re.fullmatch(r'(?:(новый|текстовый|txt|html|css|json|python|питон)\s+)?файл\s*[:：]?\s*(.*)',body,re.I|re.S)
 if not match:return None
 kind=(match[1] or '').casefold();tail=match[2]
 # Content delimiters inside a quoted filename are literal characters.
 mask=list(tail)
 for quote in QUOTES.finditer(tail):mask[quote.start():quote.end()]='X'*len(quote.group())
 delimiter=re.search(r'\s+(?:с текстом|с содержимым|с содержанием|с кодом)\s*[:：]?\s*',''.join(mask),re.I)
 if not delimiter and re.search(r'\b(?:(?:с|для)\s+(?:(?:простенькой|простой|мини|красивой|новой)\s+)?(?:игрой|игры|сайтом|сайта|кнопкой|кнопками|калькулятором|интерфейсом|анимацией|таблицей|приложением)|который|в котором|чтобы|в папке\s+)', ''.join(mask),re.I):return None
 content=tail[delimiter.end():] if delimiter else ''
 name=strip_name(tail[:delimiter.start()] if delimiter else tail)
 if len(content)>=2 and (content[0],content[-1]) in (('"','"'),('«','»'),("'","'")):content=content[1:-1]
 suffix={'текстовый':'.txt','txt':'.txt','html':'.html','css':'.css','json':'.json','python':'.py','питон':'.py'}.get(kind)
 if not name:name='Новый файл'+(suffix or '.txt')
 elif suffix and not Path(name).suffix:name+=suffix
 return {'kind':'file','name':name,'content':content,'desktop':desktop}
