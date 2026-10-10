"""Explicit desktop commands: no generated shell scripts or process killing."""
import ctypes
import os
import re
import shutil
from pathlib import Path
from .identity import identity_reply

ALIASES={'хром':'chrome','гугл хром':'chrome','google chrome':'chrome','эдж':'edge','едж':'edge','браузер':'edge','телеграм':'telegram','телеграмм':'telegram','телега':'telegram','дискорд':'discord','стим':'steam','вс код':'visual studio code','вс':'visual studio code','vscode':'visual studio code','vs code':'visual studio code','блокнот':'notepad','калькулятор':'calc','проводник':'explorer','диспетчер задач':'taskmgr','7 зип':'7zip','7-зип':'7zip'}

def normalized(value):
    return re.sub(r'[^\w]+','',value.casefold().replace('ё','е')).removesuffix('exe')

def clean_command(text):
    value=re.sub(r'^(?:привет|здравствуй|здравствуйте|пожалуйста)[,! .]+','',text.strip(),flags=re.I)
    value=re.sub(r'^(?:(?:братан|бро|ассистент|codi(?:ai)?)[, ]+)?(?:(?:можешь|можно|пожалуйста|давай|мне нужно|я хочу)\s+)+','',value,flags=re.I)
    value=re.sub(r'\s+пожалуйста[.!]?\s*$','',value,flags=re.I)
    value=re.sub(r'^(?:(?:а|и|ну|да)[, ]+)?(?:теперь|затем|после этого)[, ]+','',value,flags=re.I)
    value=re.sub(r'^(открыть|отрыть|откырть|отрыкрой|запустить|включить|включи)\b','открой',value,flags=re.I)
    value=re.sub(r'^(переименовать|переименуй мне|переименуй пожалуйста)\b','переименуй',value,flags=re.I)
    value=re.sub(r'^(создать|создавай|создат|создатьь|сделать)\b','создай',value,flags=re.I)
    value=re.sub(r'^(удалить|убери)\b','удали',value,flags=re.I)
    value=re.sub(r'^(перименуй|переменуй)\b','переименуй',value,flags=re.I)
    value=re.sub(r'^(скапируй)\b','скопируй',value,flags=re.I)
    value=re.sub(r'^(создай|сделай|удали|переименуй|открой|запусти|скопируй|перенеси|перемести)\s+пожалуйста[, ]+',r'\1 ',value,flags=re.I)
    if re.search(r'\b(?:с текстом|с содержимым|с содержанием|с кодом|запиши|напиши)\b',value,re.I):return value.strip()
    return value.strip().rstrip('!.').strip()

def quick_command(text):
    value=clean_command(text)
    if identity_reply(value):return True
    return bool(re.match(r'^(пройди|дойди|играй|создай|сделай|создайте|удали|переименуй|запиши|напиши в|открой|запусти|запомни|повтори|скопируй|копируй|перемести|перенеси|сверни|разверни|закрой|восстанови|покажи|список|найди в интернете|найди в сети|поищи в интернете|что ты помнишь|как меня зовут|какой мой|какая моя|какие мои)\b',value,re.I))

def windows():
    if os.name!='nt':raise ValueError('Управление окнами доступно в Windows')
    from ctypes import wintypes as w
    user=ctypes.WinDLL('user32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    callback=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    user.EnumWindows.argtypes=[callback,w.LPARAM];user.IsWindowVisible.argtypes=[w.HWND]
    user.GetWindowTextLengthW.argtypes=[w.HWND];user.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
    kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,ctypes.POINTER(w.DWORD)]
    kernel.CloseHandle.argtypes=[w.HANDLE];user.IsIconic.argtypes=[w.HWND]
    result=[]
    @callback
    def collect(hwnd,_):
        length=user.GetWindowTextLengthW(hwnd)
        if not length or not user.IsWindowVisible(hwnd):return True
        title=ctypes.create_unicode_buffer(length+1);user.GetWindowTextW(hwnd,title,length+1)
        if title.value in ('Program Manager','Windows Input Experience'):return True
        pid=w.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid));process=''
        handle=kernel.OpenProcess(0x1000,False,pid.value)
        if handle:
            try:
                buffer=ctypes.create_unicode_buffer(32768);size=w.DWORD(len(buffer))
                if kernel.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size)):process=Path(buffer.value).stem
            finally:kernel.CloseHandle(handle)
        result.append({'id':int(hwnd),'title':title.value,'process':process,'minimized':bool(user.IsIconic(hwnd))})
        return True
    user.EnumWindows(collect,0)
    return result

def window_action(action,query,inventory=None):
    items=windows() if inventory is None else inventory
    query=re.sub(r'^(?:окно|программу|приложение)\s+','',query,flags=re.I).strip('«»" ')
    keys={normalized(query),normalized(ALIASES.get(query.casefold(),query))}
    matches=[item for item in items if any(key and (key==normalized(item['process']) or key==normalized(item['title'])) for key in keys)]
    matches=matches or [item for item in items if any(key and (key in normalized(item['title']) or key in normalized(item['process'])) for key in keys)]
    if len(matches)!=1:return {'reply':'Уточните окно: '+('; '.join(item['title'] for item in matches[:6]) if matches else 'подходящее окно не найдено. Напишите «покажи окна».')}
    item=matches[0]
    if 'codiai' in normalized(item['title']) or item['process'].casefold() in ('codex','system','winlogon'):
        return {'reply':'Для этого окна используйте его обычные кнопки управления.'}
    from ctypes import wintypes as w
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];user.ShowWindowAsync.argtypes=[w.HWND,ctypes.c_int]
    if action=='close':
        if not user.PostMessageW(item['id'],0x10,0,0):raise ValueError('Windows не разрешила закрыть это окно')
        reply='Отправлен запрос закрытия: '+item['title']+'. Если есть несохранённые данные, программа покажет свой диалог.'
    else:
        code={'minimize':6,'maximize':3,'restore':9}.get(action)
        if code is None:raise ValueError('Неизвестное действие с окном')
        if not user.ShowWindowAsync(item['id'],code):raise ValueError('Не удалось изменить состояние окна')
        reply={'minimize':'Сворачиваю: ','maximize':'Разворачиваю: ','restore':'Восстанавливаю: '}[action]+item['title']
    return {'reply':reply,'action':{'type':'window','operation':action,'title':item['title']}}

class Controls:
    def rename(self,source,name,context):
        source=re.sub(r'^(?:файл|папку|документ)\s+','',source,flags=re.I)
        from .file_commands import strip_name
        path=self.target(source,context);name=self.folder_name(strip_name(name))
        if path.is_file() and path.suffix and not Path(name).suffix:name+=path.suffix
        destination=path.with_name(name)
        if destination==path:return {'reply':'Имя уже установлено: '+str(path),'context':context}
        if destination.exists():raise ValueError('Файл с таким именем уже существует: '+str(destination))
        path.rename(destination)
        if path.exists() or not destination.exists():raise ValueError('Переименование не подтверждено на диске: '+str(destination))
        return {'reply':'Переименовано: '+str(destination),'action':{'type':'rename','old_path':str(path),'path':str(destination)},'context':{'folder':str(destination if destination.is_dir() else destination.parent),**({'file':str(destination)} if destination.is_file() else {})}}

    def copy_move(self,source,destination,context,move=False):
        source=re.sub(r'^(?:файл|папку|документ)\s+','',source,flags=re.I)
        path=self.target(source,context)
        destination=destination.strip('«»" ')
        if destination.casefold() in ('рабочий стол','на рабочий стол'):folder=self.desktop_folder()
        else:
            destination=re.sub(r'^(?:папку|каталог)\s+','',destination,flags=re.I)
            folder=self.target(destination,context)
        if not folder.is_dir():raise ValueError('Место назначения должно быть папкой')
        target=folder/path.name
        if target.exists():raise ValueError('В папке назначения уже есть '+path.name)
        if folder.resolve().is_relative_to(path.resolve()):raise ValueError('Нельзя поместить папку внутрь неё самой')
        if path.is_dir():
            count=0
            for root,dirs,files in os.walk(path,followlinks=False):
                count+=len(dirs)+len(files)
                if count>5000:raise ValueError('Папка содержит больше 5000 объектов; используйте Проводник')
                for name in dirs+files:
                    child=Path(root)/name
                    if child.is_symlink() or (hasattr(child,'is_junction') and child.is_junction()):raise ValueError('Внутри папки есть ссылка или junction; выберите отдельные файлы')
        if move:shutil.move(str(path),str(target))
        elif path.is_dir():shutil.copytree(path,target)
        else:shutil.copy2(path,target)
        return {'reply':('Перемещено: ' if move else 'Скопировано: ')+str(target),'action':{'type':'move' if move else 'copy','old_path':str(path),'path':str(target)},'context':{'folder':str(target if target.is_dir() else target.parent),**({'file':str(target)} if target.is_file() else {})}}

    def extra_command(self,value,context):
        if re.fullmatch(r'(?:покажи|список)(?: мне)?\s+(?:окна|окон|открытые окна|открытых окон)',value,re.I):
            items=windows()
            return {'reply':'Открытые окна:\n'+'\n'.join(item['title']+(' — свёрнуто' if item['minimized'] else '') for item in items),'windows':items}
        match=re.fullmatch(r'(сверни|разверни|восстанови|закрой)\s+(.+)',value,re.I)
        if match:return window_action({'сверни':'minimize','разверни':'maximize','восстанови':'restore','закрой':'close'}[match[1].lower()],match[2])
        match=re.fullmatch(r'(?:скопируй|копируй|перемести|перенеси)\s+(.+?)\s+(?:в|на)\s+(.+)',value,re.I)
        if match:return self.copy_move(match[1],match[2],context,move=bool(re.match('перемести|перенеси',value,re.I)))
        match=re.fullmatch(r'переименуй\s+(.+?)\s+(?:в|на)\s+(.+)',value,re.I)
        if match:return self.rename(match[1],match[2],context)
        if re.fullmatch(r'(?:покажи|список)(?: мне)?\s+(?:программы|программ|приложения|приложений)',value,re.I):return {'reply':'Установленные программы:\n'+'\n'.join(a['name'] for a in self.apps())}
        match=re.fullmatch(r'(?:покажи|открой)\s+(?:папку\s+)?(рабочий стол|загрузки|документы)',value,re.I)
        if match:
            folder=self.desktop_folder() if match[1].lower()=='рабочий стол' else Path.home()/('Downloads' if match[1].lower()=='загрузки' else 'Documents')
            if not folder.is_dir():raise ValueError('Эта папка не найдена; укажите путь')
            os.startfile(str(folder));return {'reply':'Открыта папка: '+str(folder),'context':{'folder':str(folder)}}
        match=re.fullmatch(r'(?:открой|покажи)\s+(настройки(?:\s+звука|\s+сети|\s+экрана)?|параметры windows)',value,re.I)
        if match:
            uri={'настройки звука':'ms-settings:sound','настройки сети':'ms-settings:network','настройки экрана':'ms-settings:display'}.get(match[1].lower(),'ms-settings:')
            os.startfile(uri);return {'reply':'Открыты '+match[1]}
        match=re.fullmatch(r'(?:открой|запусти)\s+(https?://\S+)',value,re.I)
        if match:
            from .web_sources import public_url
            url,_=public_url(match[1]);os.startfile(url);return {'reply':'Открыта ссылка: '+url}
        return None
