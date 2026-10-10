"""File confirmations are produced from write receipts, never model claims."""
import re
from pathlib import Path
from .tools import digest

FILE=re.compile(r'файл|html|страниц|сайт|игр[ау]|приложени|код|скрипт|модел|персонаж|иллюстрац|рисунок|svg|\.(?:py|js|ts|css|json|txt|md|html)\b',re.I)

def claims_written(text):
 return bool(FILE.search(text) and re.search(r'создан|создал[аи]?\b|записан|записал[аи]?\b|сохран[её]н|сохранил[аи]?\b|готов[ао]?\s+к\s+использованию',text,re.I))

def needs_file(text):
 if re.search(r'\b(?:не создавай|не записывай|не меняй|только объясни|объясни как|как создать|покажи пример)\b',text,re.I):return False
 return bool(FILE.search(text) and re.search(r'созда[йт]|сдела[йт]|исправ|поправ|измени|запиши|сохрани',text,re.I))

def receipts(calls):
 records={}
 for call in calls:
  result=call['result'];data=result.get('result',{})
  if call['name']=='propose_write' and result.get('status')=='ok' and data.get('file_written'):
   records[data.get('absolute_path',data['path'])]=data
 valid=[];failed=[]
 for path,data in records.items():
  target=Path(path)
  try:verified=target.is_absolute() and target.is_file() and data.get('read_back_verified') is True and digest(target.read_bytes())==data.get('sha256')
  except OSError:verified=False
  (valid if verified else failed).append(str(target))
 return valid,failed

def failed_write_message(calls,tools_enabled):
 errors=[c['result']['error'] for c in calls if c['result'].get('status')=='error']
 reason=(' Последняя ошибка: '+errors[-1][:450]) if errors else ''
 if not tools_enabled:reason=' Включите «Действия» и выберите папку проекта.'
 return 'Создание или изменение файла не подтверждено. Сообщение модели не означает запись на диск.'+reason
