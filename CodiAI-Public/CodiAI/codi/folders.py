"""User-operated Windows folder selection. No shell command interpolation."""
import json
import os
import subprocess
import threading
from .config import ROOT

class FolderPicker:
    def __init__(self):
        self.lock=threading.Lock()

    def choose(self, current=''):
        if os.name!='nt':
            raise ValueError('В этом окружении укажите путь вручную')
        if not self.lock.acquire(blocking=False):
            raise ValueError('Окно выбора папки уже открыто')
        try:
            environment={**os.environ,'CODIAI_SELECTED_FOLDER':current}
            result=subprocess.run(['powershell.exe','-NoProfile','-STA','-ExecutionPolicy','Bypass','-File',str(ROOT/'Pick-Project.ps1')],env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW,timeout=180)
            if result.returncode:
                raise ValueError('Не удалось открыть выбор папки. Можно вставить путь вручную')
            return json.loads(result.stdout.decode('utf-8-sig'))
        except subprocess.TimeoutExpired as exc:
            raise ValueError('Выбор папки не завершён. Нажмите кнопку ещё раз') from exc
        finally:
            self.lock.release()
