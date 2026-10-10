"""Local desktop actions and language-triggered memory. No arbitrary shell code."""
import ctypes
import json
import os
import re
import subprocess
from pathlib import Path
from .storage import new_id
from .identity import identity_reply
import time
import threading
from .desktop_controls import Controls, ALIASES, normalized, clean_command

class Desktop(Controls):
    def __init__(self,store,images):
        self.store,self.images=store,images
        self.app_cache=None
        self.apps_lock=threading.Lock()

    def apps(self):
        with self.apps_lock:
            if self.app_cache is not None:return self.app_cache
            roots=[Path(os.environ.get('ProgramData','C:/ProgramData'))/'Microsoft/Windows/Start Menu/Programs',Path(os.environ.get('APPDATA',''))/'Microsoft/Windows/Start Menu/Programs',self.desktop_folder() if os.name=='nt' else Path.home()/'Desktop']
            found={}
            for root in roots:
                if root.is_dir():
                    for p in (root.glob('*.lnk') if root==roots[-1] else root.rglob('*.lnk')):
                        if not any(word in p.stem.lower() for word in ('uninstall','удаление','деинстал')):found[normalized(p.stem)]={'name':p.stem,'path':str(p)}
            for name,exe in [('Блокнот','notepad'),('Калькулятор','calc'),('Проводник','explorer'),('Диспетчер задач','Taskmgr'),('Paint','mspaint'),('Ножницы','SnippingTool')]:
                path=Path(os.environ.get('WINDIR','C:/Windows'))/('explorer.exe' if exe=='explorer' else 'System32/'+exe+'.exe')
                if path.exists():found[normalized(name)]={'name':name,'path':str(path)}
            if os.name=='nt':
                import winreg
                for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
                    for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
                        try:
                            with winreg.OpenKey(hive,r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths',0,winreg.KEY_READ|view) as key:
                                for index in range(winreg.QueryInfoKey(key)[0]):
                                    name=winreg.EnumKey(key,index)
                                    try:
                                        with winreg.OpenKey(key,name) as item:location=Path(winreg.QueryValue(item,None).strip('"'))
                                        if location.is_file() and location.suffix.lower()=='.exe' and not any(part in name.lower() for part in ('uninst','setup')):
                                            found.setdefault(normalized(name),{'name':location.stem,'path':str(location)})
                                    except OSError:pass
                        except OSError:pass
                script="[Console]::OutputEncoding=[Text.UTF8Encoding]::new();Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"
                try:
                    result=subprocess.run(['powershell.exe','-NoProfile','-Command',script],stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW,timeout=8)
                    entries=json.loads(result.stdout.decode('utf-8-sig')) if not result.returncode else []
                    if isinstance(entries,dict):entries=[entries]
                    for item in entries:
                        if '!' in item['AppID']:found.setdefault(normalized(item['Name']),{'name':item['Name'],'path':'shell:AppsFolder\\'+item['AppID']})
                except (OSError,ValueError,subprocess.TimeoutExpired):pass
            self.app_cache=sorted(found.values(),key=lambda a:a['name'].lower())
            return self.app_cache

    def folder_name(self,value):
        name=value.strip().strip('"\u00ab\u00bb').strip("'")
        if not name or name in ('.','..') or re.search(r'[<>:"/\\|?*\x00-\x1f]',name) or name.endswith(('.', ' ')) or re.fullmatch(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',name,re.I):
            raise ValueError('Укажите обычное имя без символов пути, например «Мой проект»')
        return name

    def desktop_folder(self):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
            value=winreg.QueryValueEx(key,'Desktop')[0]
        return Path(os.path.expandvars(value)).resolve(strict=True)

    def create_folder(self,value,context,on_desktop=False):
        from .file_commands import strip_name
        value=strip_name(value)
        requested=Path(value)
        if requested.is_absolute():
            path=requested
            if path==Path(path.anchor):raise ValueError('Укажите имя новой папки, а не весь диск')
            for part in path.parts[1:]:self.folder_name(part)
            cursor=path
            while cursor!=Path(path.anchor):
                if cursor.is_symlink() or (hasattr(cursor,'is_junction') and cursor.is_junction()):raise ValueError('Создание через ссылку или junction не выполняется')
                cursor=cursor.parent
            existed=path.is_dir();path.mkdir(parents=True,exist_ok=True)
            return {'reply':('Папка уже существует: ' if existed else 'Создана папка: ')+str(path),'action':{'type':'mkdir','path':str(path)}}
        name=self.folder_name(value)
        root=self.desktop_folder() if on_desktop else Path(context.get('folder') or self.store.settings()['workspace'] or self.desktop_folder())
        root=root.resolve(strict=True);path=root/name
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):raise ValueError('На этом месте уже находится ссылка')
        existed=path.is_dir();path.mkdir(exist_ok=True)
        return {'reply':('Папка уже существует: ' if existed else 'Создана папка: ')+str(path),'action':{'type':'mkdir','path':str(path)}}

    def destination(self,name,context,on_desktop=False):
        requested=Path(name)
        if requested.is_absolute():path=requested
        else:
            selected=context.get('folder') or (str(Path(context['file']).parent) if context.get('file') else '')
            root=self.desktop_folder() if on_desktop else Path(selected or self.store.settings()['workspace'] or self.desktop_folder())
            root=root.resolve(strict=True)
            if requested.drive or '..' in requested.parts:raise ValueError('Укажите путь внутри выбранной папки или полный путь')
            path=root/requested
        if path==Path(path.anchor):raise ValueError('Укажите имя файла или папки')
        for part in path.parts[1:]:self.folder_name(part)
        cursor=path
        while cursor!=Path(path.anchor):
            if cursor.is_symlink() or (hasattr(cursor,'is_junction') and cursor.is_junction()):raise ValueError('Создание через ссылку или junction не выполняется')
            cursor=cursor.parent
        return path

    def folder_command(self,value,context):
        from .file_commands import parse_create
        parsed=parse_create(value)
        if not parsed or parsed['kind']!='folder':return None
        name=parsed['name']
        if not name:
            root=self.destination('Новая папка',context,parsed['desktop']).parent
            name='Новая папка';number=2
            while (root/name).exists():name=f'Новая папка ({number})';number+=1
        path=self.destination(name,context,parsed['desktop'])
        if path.exists() and not path.is_dir():raise ValueError('На этом месте уже существует файл: '+str(path))
        result=self.create_folder(str(path),{},False);result['context']={'folder':str(path)}
        return result

    def file_command(self,value,context):
        from .file_commands import parse_create
        from .tools import BINARY_SUFFIXES
        parsed=parse_create(value)
        if not parsed or parsed['kind']!='file':return None
        name=parsed['name'];content=parsed['content']
        path=self.destination(name,context,parsed['desktop'])
        if path.suffix.lower() in BINARY_SUFFIXES|{'.sys','.lnk'}:raise ValueError('Этот формат двоичный. Создайте исходный код; APK и программы получают сборкой')
        if path.exists():raise ValueError('Файл уже существует: '+str(path)+'. Для изменения напишите «запиши в этот файл …»')
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x',encoding='utf-8',newline='') as stream:stream.write(content)
        if path.read_bytes()!=content.encode('utf-8'):raise ValueError('Запись файла не подтверждена проверкой содержимого: '+str(path))
        return {'reply':'Создан файл: '+str(path),'action':{'type':'write','path':str(path)},'context':{'file':str(path),'folder':str(path.parent)}}

    def launch(self,name):
        import difflib
        name=name.strip('«»" ');key=normalized(ALIASES.get(name.casefold(),name));apps=self.apps()
        builtins={'notepad':'блокнот','calc':'калькулятор','explorer':'проводник','taskmgr':'диспетчер задач'}
        key=normalized(builtins.get(key,key))
        matches=[a for a in apps if key==normalized(a['name']) or key==normalized(Path(a['path']).stem)]
        matches=matches or [a for a in apps if key and normalized(a['name']).startswith(key)]
        matches=matches or [a for a in apps if key and key in normalized(a['name'])]
        unique={a['path'].casefold():a for a in matches};matches=list(unique.values())
        if len(matches)>1:
            # Registry executable and Start Menu shortcut can represent the same app.
            linked=[a for a in matches if a['path'].lower().endswith('.lnk')]
            if len(linked)==1:matches=linked
        if len(matches)!=1:
            suggestions=matches or [a for a in apps if difflib.SequenceMatcher(None,key,normalized(a['name'])).ratio()>=0.55]
            return {'reply':'Программа не определена однозначно. '+('Подходят: '+', '.join(a['name'] for a in suggestions[:8]) if suggestions else 'Нажмите «Программы» и выберите её или укажите полный путь .exe.'),'action':None}
        app=matches[0];os.startfile(app['path'])
        return {'reply':'Отправлена команда запуска: '+app['name'],'action':{'type':'launch','name':app['name']}}

    def target(self,value,context):
        value=value.strip().strip('"«»').strip("'")
        if value.lower() in ('этот файл','этот документ','этот','его','её','ее','её папку','последнюю папку','созданную папку','эту папку','этот каталог'):
            value=context.get('file','') or context.get('folder','')
        if value and not Path(value).is_absolute():
            on_desktop='на рабочем столе' in value.lower()
            value=re.sub(r'\bна рабочем столе\b','',value,flags=re.I).strip().strip('«»"')
            roots=[self.desktop_folder()] if on_desktop else [Path(context['folder'])] if context.get('folder') else [Path(self.store.settings()['workspace'])] if self.store.settings()['workspace'] else [self.desktop_folder()]
            candidates=[root/self.folder_name(value) for root in roots]
            existing=[candidate for candidate in candidates if candidate.exists()]
            if len(existing)==1:value=str(existing[0])
        if not value or not Path(value).is_absolute():
            raise ValueError('Файл не найден в выбранной папке. Укажите полный путь или выберите его кнопкой «Файл»')
        path=Path(os.path.abspath(value))
        if not path.exists():raise ValueError('Файл или папка не найдены: '+str(path))
        if path==Path(path.anchor):raise ValueError('Выберите отдельный файл или папку, не весь диск')
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
            raise ValueError('Выберите сам файл, а не ссылку или junction')
        return path

    def recycle(self,path):
        if os.name!='nt':raise ValueError('Корзина доступна в Windows')
        task_script="""$ErrorActionPreference='Stop';Add-Type -AssemblyName Microsoft.VisualBasic;$p=$env:CODIAI_RECYCLE_TARGET;if([IO.Directory]::Exists($p)){[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($p,[Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,[Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin)}else{[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($p,[Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,[Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin)}"""
        drive=path.drive
        if drive.startswith('\\\\'):raise ValueError('Для сетевых файлов Корзина недоступна. Выберите файл на локальном диске')
        if ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor))!=3:
            raise ValueError('Корзина доступна для файлов на локальных дисках C и D, а не сетевых или съёмных дисках')
        environment={**os.environ,'CODIAI_RECYCLE_TARGET':str(path)}
        result=subprocess.run(['powershell.exe','-NoProfile','-Command',task_script],env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW,timeout=60)
        if result.returncode or path.exists():raise ValueError('Windows не завершила удаление. Проверьте, не открыт ли файл и есть ли права доступа')
        return {'reply':'Перемещено в Корзину: '+str(path),'action':{'type':'recycle','path':str(path)}}

    def explorer_context(self):
        """Read selected items from Explorer, without moving focus or clicking."""
        script="[Console]::OutputEncoding=[Text.UTF8Encoding]::new();$ErrorActionPreference='Stop';$s=New-Object -ComObject Shell.Application;$items=@();foreach($w in $s.Windows()){if($w.FullName -like '*explorer.exe'){foreach($i in $w.Document.SelectedItems()){$items+=@{path=$i.Path;folder=$i.IsFolder}}}};ConvertTo-Json -InputObject @($items) -Compress"
        result=subprocess.run(['powershell.exe','-NoProfile','-Command',script],stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW,timeout=8)
        if result.returncode:return {}
        try:items=json.loads(result.stdout.decode('utf-8-sig'))
        except (ValueError,UnicodeError):return {}
        if len(items)!=1:return {}
        return {'folder' if items[0]['folder'] else 'file':items[0]['path']}

    def record(self,chat_id,action,reply):
        self.store.audit('desktop_action',json.dumps({'chat_id':chat_id,'action':action,'reply':reply},ensure_ascii=False))

    def last_action(self,chat_id=None):
        with self.store.db() as db:
            rows=db.execute("SELECT detail FROM audit WHERE action='desktop_action' ORDER BY created DESC LIMIT 30").fetchall()
        for row in rows:
            item=json.loads(row['detail'])
            if item.get('action') and (chat_id is None or item['chat_id']==chat_id):return item['action']
        return None

    def remember(self,text,chat):
        content=re.sub(r'^запомни(?:\s+это)?\s*[:,-]?\s*','',text,flags=re.I).strip()
        if not content:
            previous=chat['messages'][-1] if chat['messages'] else None
            if not previous:raise ValueError('Напишите, что нужно запомнить')
            content=previous['content']
            action=previous.get('metadata',{}).get('desktop_action')
            if action:content+='\nПорядок действий: '+json.dumps(action,ensure_ascii=False)
            elif previous.get('metadata',{}).get('tools'):
                task=next((m['content'] for m in reversed(chat['messages'][:-1]) if m['role']=='user'),'')
                steps=[{'name':t['name'],'path':t.get('arguments',{}).get('path','')} for t in previous['metadata']['tools'] if t['result']['status']=='ok']
                content='Задача: '+task+'\nПорядок действий: '+json.dumps(steps,ensure_ascii=False)+'\nРезультат: '+content
        content=content[:2000]
        with self.store.db() as db:
            scope='story:'+chat['id'] if chat['mode']=='roleplay' else 'preferences'
            db.execute('INSERT INTO memories VALUES(?,?,?,?,?)',(new_id(),scope,content,time.time(),'user'))
        settings=self.store.settings();self.store.save_settings({**settings,'memory_enabled':True})
        return {'reply':'Запомнила: '+content,'action':None}

    def command(self,text,context,chat):
        if not isinstance(context,dict):raise ValueError('Неверный контекст компьютера')
        from .chat_context import chat_context
        context=context or chat_context(chat)
        value=clean_command(text)
        from .file_commands import split_commands
        parts=split_commands(value)
        if len(parts)>1:
            selected=dict(context);replies=[];last=None
            for part in parts:
                result=self.command(part,selected,chat)
                if result is None:
                    if not replies:return None
                    replies.append('Уточните следующую команду: '+part);break
                replies.append(result['reply'])
                if result.get('context'):selected=dict(result['context'])
                last=result
            return {'reply':'\n'.join(replies),'context':selected,'action':last.get('action') if last else None}
        identity=identity_reply(value)
        if identity:return {'reply':identity,'action':None}
        if re.match(r'^(?:пройди|дойди|играй)\b',value,re.I) and hasattr(self,'game'):
            return {'reply':'Для управления нажмите «Игра» в помощнике, выберите окно запущенной игры и введите эту задачу. Использую изученные материалы и экран выбранного окна.','action':None}
        if re.match(r'^запомни\b',value,re.I):return self.remember(value,chat)
        if re.fullmatch(r'(?:что ты (?:помнишь|запомнила|запомнил)(?: обо мне)?|как меня зовут|(?:какой|какая|какие) мо[йяи] .+|покажи (?:свою )?память)',value,re.I):
            scope='story:'+chat['id'] if chat['mode']=='roleplay' else 'preferences'
            items=self.store.relevant_memories(scope,value,5)
            return {'reply':('Сохранено в памяти:\n'+'\n'.join('• '+item['content'] for item in items)) if items else 'В этой области памяти записей пока нет. Напишите «запомни: …».','action':None}
        if chat['mode']!='roleplay' or 'на рабочем столе' in value.lower() or re.search(r'[A-Za-z]:[\\/]',value):
            folder=self.folder_command(value,context)
            if folder is not None:return folder
        if chat['mode']=='desktop' and re.fullmatch(r'(?:сделай|повтори)(?: это)? как в прошлый раз[.!]?',value,re.I):
            action=self.last_action(chat['id']) or self.last_action()
            if not action:
                if any(m.get('metadata',{}).get('tools') for m in chat['messages']):return None
                return {'reply':'Пока нет сохранённого действия. Выполните его один раз и напишите «запомни это».','action':None}
            if action['type']=='launch':return self.launch(action['name'])
            if action['type']=='website':
                from .web_sources import public_url
                import webbrowser
                address,_=public_url(action['url'])
                if not webbrowser.open(address):raise ValueError('Не удалось открыть браузер')
                return {'reply':'Открываю сайт: '+address,'action':action}
            if action['type']=='recycle':return self.recycle(self.target(context.get('file') or action['path'],context))
            if action['type']=='open':
                path=self.target(context.get('file') or action['path'],context);os.startfile(str(path))
                return {'reply':'Открыто: '+str(path),'action':{'type':'open','path':str(path)}}
            if action['type']=='mkdir':return self.create_folder(Path(action['path']).name,{'folder':str(Path(action['path']).parent)})
            if action['type']=='rename':return {'reply':'Для следующего переименования выберите файл и напишите «переименуй этот файл в новое имя».','action':None}
        if chat['mode']=='roleplay':return None
        if os.name=='nt' and not context and re.search(r'этот файл|этот документ|эту папку',value,re.I):context=self.explorer_context()
        extra=self.extra_command(value,context)
        if extra is not None:return extra
        match=re.fullmatch(r'(?:запиши|напиши)\s+в\s+(этот файл|этот документ)\s+(?:текст\s*[:：]?\s*)?(.+)',value,re.I|re.S)
        if match:
            import shutil
            path=self.target(match.group(1),context)
            from .tools import BINARY_SUFFIXES
            if not path.is_file() or path.suffix.lower() in BINARY_SUFFIXES|{'.sys','.lnk'}:raise ValueError('Выберите текстовый файл')
            with path.open('rb') as stream:
                if b'\0' in stream.read(8192):raise ValueError('Выберите текстовый файл')
            backup=self.store.path.parent/'backups'
            backup.mkdir(parents=True,exist_ok=True);saved=backup/(new_id()+'-'+path.name);shutil.copy2(path,saved)
            path.write_text(match.group(2),encoding='utf-8',newline='')
            if path.read_bytes()!=match.group(2).encode('utf-8'):raise ValueError('Запись файла не подтверждена проверкой содержимого: '+str(path))
            return {'reply':'Записан файл: '+str(path)+'\nПредыдущая версия: '+str(saved),'action':{'type':'write','path':str(path),'backup':str(saved)},'context':context}
        created=self.file_command(value,context)
        if created is not None:return created
        match=re.fullmatch(r'переименуй\s+(этот файл|этот документ|эту папку)\s+в\s+(.+)',value,re.I)
        if match:
            path=self.target(match.group(1),context);destination=path.with_name(self.folder_name(match.group(2)))
            if destination.exists():raise ValueError('Файл с таким именем уже существует')
            path.rename(destination)
            return {'reply':'Переименовано: '+str(destination),'action':{'type':'rename','old_path':str(path),'path':str(destination)},'context':{'folder' if destination.is_dir() else 'file':str(destination)}}
        match=re.match(r'^(?:запусти|открой)\s+(.+?)\s*[.!]?$',value,re.I)
        if match:
            name=re.sub(r'^(?:программу|приложение)\s+','',match.group(1).strip(),flags=re.I)
            site_key=re.sub(r'[\s-]+','',name.casefold().strip('«»"'))
            sites={'chatgpt':'https://chatgpt.com','чатгпт':'https://chatgpt.com','чатджипити':'https://chatgpt.com','youtube':'https://www.youtube.com','ютуб':'https://www.youtube.com','claude':'https://claude.ai','клод':'https://claude.ai'}
            if site_key in sites or re.match(r'^https?://',name,re.I):
                from .web_sources import public_url
                address=sites.get(site_key,name);address,_=public_url(address)
                import webbrowser
                if not webbrowser.open(address):raise ValueError('Не удалось открыть браузер')
                return {'reply':'Открываю сайт: '+address,'action':{'type':'website','url':address}}
            if name.lower() in ('этот файл','этот документ','эту папку','этот каталог','её','ее','его') or Path(name.strip('"')).is_absolute() or re.match(r'^(файл|папку|документ)\s+',name,re.I):
                name=re.sub(r'^(?:файл|папку|документ)\s+','',name,flags=re.I)
                path=self.target(name,context);os.startfile(str(path))
                return {'reply':'Открыто: '+str(path),'action':{'type':'open','path':str(path)}}
            return self.launch(name)
        match=re.match(r'^удали(?:ть)?\s+(.+)$',value,re.I)
        if match:
            target=match.group(1).strip()
            if target.lower().startswith(('программу ','приложение ')):
                os.startfile('ms-settings:appsfeatures')
                return {'reply':'Открыт список установленных приложений Windows. Выберите '+target.split(' ',1)[1]+' и подтвердите удаление в штатном деинсталляторе.','action':None}
            target=re.sub(r'^(?:файл|папку)\s+','',target,flags=re.I)
            return self.recycle(self.target(target,context))
        return None
