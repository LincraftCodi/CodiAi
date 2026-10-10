"""Native browser lifecycle and transient navigation queue."""
import collections
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from .config import ROOT
from .web_sources import public_url

class Browser:
    def __init__(self):
        self.lock=threading.Lock();self.commands=collections.deque(maxlen=20);self.process=None;self.last_seen=0;self.current_url=''
    def open(self,url='https://duckduckgo.com/'):
        if os.name!='nt':raise ValueError('Полный встроенный браузер доступен в Windows; режим чтения работает здесь')
        url,_=public_url(url)
        with self.lock:
            if not self.process or self.process.poll() is not None:
                self.process=subprocess.Popen([str(Path(sys.executable).with_name('pythonw.exe')),str(ROOT/'browser_host.py'),url],cwd=ROOT,creationflags=subprocess.CREATE_NO_WINDOW)
            else:self.commands.append({'type':'navigate','url':url})
        return {'opened':True,'url':url}
    def navigate_if_open(self,url):
        with self.lock:
            if time.monotonic()-self.last_seen<5:self.commands.append({'type':'navigate','url':url})
    def heartbeat(self,url=''):
        with self.lock:
            self.last_seen=time.monotonic();self.current_url=url[:3000];commands=list(self.commands);self.commands.clear()
        return {'commands':commands}
    def state(self):return {'open':time.monotonic()-self.last_seen<5,'url':self.current_url}
