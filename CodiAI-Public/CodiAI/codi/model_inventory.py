"""Check model manifests and referenced blob sizes without loading weights."""
import json
import re
from pathlib import Path

def local_state(root,name):
    root=Path(root)
    base,tag=name.rsplit(':',1) if ':' in name else (name,'latest')
    if not re.fullmatch(r'[\w./-]+',base) or not re.fullmatch(r'[\w.-]+',tag):return {'installed':False,'reason':'Неверное название модели'}
    paths=[root/'manifests-v2/ollama.com/library'/base/tag,root/'manifests/registry.ollama.ai/library'/base/tag]
    def read(path,depth=0):
        if depth>4:raise ValueError('Слишком глубокий манифест')
        data=json.loads(path.read_text(encoding='utf-8'))
        if data.get('manifests'):
            errors=[]
            for item in data['manifests']:
                try:return read(blob(item['digest']),depth+1)
                except (OSError,ValueError,KeyError) as exc:errors.append(str(exc))
            raise ValueError('; '.join(errors)[:500])
        layers=data.get('layers',[])
        if not any('image.model' in item.get('mediaType','') for item in layers):raise ValueError('В манифесте нет весов')
        total=0
        for item in [data['config']]+layers:
            path=blob(item['digest']);size=path.stat().st_size
            if size!=item['size']:raise ValueError('Файл модели неполный: '+path.name)
            total+=size
        return {'installed':True,'reason':'Файлы на диске проверены по наличию и размеру','disk_bytes':total}
    def blob(digest):
        if not re.fullmatch(r'sha256:[a-f0-9]{64}',digest):raise ValueError('Неверный digest')
        return root/'blobs'/digest.replace(':','-')
    for path in paths:
        if path.exists():
            try:return read(path)
            except (OSError,ValueError,KeyError) as exc:return {'installed':False,'reason':'Нужно восстановить загрузку: '+str(exc)[:300]}
    return {'installed':False,'reason':'Файлы модели на диске D не найдены'}
