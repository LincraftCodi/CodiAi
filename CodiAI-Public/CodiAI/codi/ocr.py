"""Offline Windows OCR for validated uploaded images; no desktop capture here."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

class WindowsOCR:
    def __init__(self,images):
        self.images=images;self.cache={}
    def read(self,ident):
        if os.name!='nt':return None
        self.images.get(ident)
        key=hashlib.sha256(self.images.bytes(ident)).hexdigest()
        if key in self.cache:return self.cache[key]
        environment={**os.environ,'CODIAI_OCR_IMAGE':str((self.images.directory/(ident+'.jpg')).resolve())}
        try:
            response=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',Path(__file__).with_name('windows_ocr.ps1').read_text(encoding='utf-8')],env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW,timeout=16)
            result=json.loads(response.stdout.decode('utf-8-sig')) if not response.returncode else None
            if not isinstance(result,dict) or not isinstance(result.get('text'),str) or len(result['text'].strip())<4:result=None
            elif len(result['text'])>12000:result={**result,'text':result['text'][:12000]+'\n[Текст сокращён; выделите меньшую область.]'}
        except (OSError,ValueError,subprocess.TimeoutExpired):result=None
        if len(self.cache)>=32:self.cache.pop(next(iter(self.cache)))
        self.cache[key]=result
        return result
