"""Versioned, portable, additive memory transfer; never imports permissions or code."""
import hashlib
import json
import math
import re
import sqlite3
import time
from contextlib import closing
from .storage import new_id

FORMAT='CodiAI-memory-v1'
TABLES=('memories','documents','chunks','learning_sources')
FIELDS={
 'memories':('id','scope','content','created','source'),
 'documents':('id','name','created'),
 'chunks':('id','document_id','position','content'),
 'learning_sources':('id','job_id','url','title','summary','method','document_id','memory_id','created')}
def checksum(payload):
    # JSON round-trips through a browser turn 1.0 into 1. Canonicalize numbers
    # by their IEEE value so a valid downloaded bundle survives that round-trip.
    def canonical(value):
        if isinstance(value,(int,float)) and not isinstance(value,bool):return {'$number':float(value or 0).hex()}
        if isinstance(value,dict):return {k:canonical(v) for k,v in value.items()}
        if isinstance(value,(list,tuple)):return [canonical(v) for v in value]
        return value
    try:encoded=json.dumps(canonical(payload),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    except (TypeError,OverflowError,RecursionError) as exc:raise ValueError('Неверная структура файла памяти') from exc
    return hashlib.sha256(encoded).hexdigest()
def export_memory(store):
    with store.db() as db:
        db.execute('BEGIN')
        payload={t:[dict(r) for r in db.execute('SELECT '+','.join(FIELDS[t])+' FROM '+t)] for t in TABLES}
    documents={r['id'] for r in payload['documents']};memories={r['id'] for r in payload['memories']}
    for row in payload['learning_sources']:
        if row['document_id'] not in documents:row['document_id']=None
        if row['memory_id'] not in memories:row['memory_id']=None
    return {'format':FORMAT,'version':1,'exported_at':time.time(),'payload':payload,'sha256':checksum(payload)}

def validate_bundle(bundle):
    if not isinstance(bundle,dict) or bundle.get('format')!=FORMAT or bundle.get('version')!=1:raise ValueError('Нужен файл памяти CodiAI версии 1')
    data=bundle.get('payload')
    if not isinstance(data,dict) or set(data)!=set(TABLES):raise ValueError('В файле памяти отсутствуют необходимые разделы')
    if checksum(data)!=bundle.get('sha256'):raise ValueError('Файл памяти повреждён: контрольная сумма не совпадает')
    ids={};total=0
    limits={'memories':10000,'documents':2000,'chunks':40000,'learning_sources':10000}
    sizes={'scope':2048,'content':16000,'name':240,'source':80,'url':3000,'title':240,'summary':10000,'method':80}
    for table in TABLES:
        rows=data[table]
        if not isinstance(rows,list) or len(rows)>limits[table]:raise ValueError('Слишком много записей в файле памяти')
        ids[table]=set()
        for row in rows:
            if not isinstance(row,dict) or set(row)!=set(FIELDS[table]):raise ValueError('Неверный формат записи '+table)
            if not isinstance(row['id'],str) or not re.fullmatch('[a-f0-9]{32}',row['id']) or row['id'] in ids[table]:raise ValueError('Неверный или повторяющийся идентификатор записи')
            ids[table].add(row['id'])
            for key,max_size in sizes.items():
                if key in row:
                    if not isinstance(row[key],str) or len(row[key])>max_size or '\x00' in row[key]:raise ValueError('Слишком длинное или неверное поле '+key)
                    total+=len(row[key])
            if 'created' in row and (isinstance(row['created'],bool) or not isinstance(row['created'],(int,float)) or not math.isfinite(row['created'])):raise ValueError('Неверная дата записи')
            if 'position' in row and (isinstance(row['position'],bool) or not isinstance(row['position'],int) or not 0<=row['position']<=10000):raise ValueError('Неверный номер фрагмента')
            for key in ('document_id','memory_id'):
                if key in row and row[key] is not None and (not isinstance(row[key],str) or not re.fullmatch('[a-f0-9]{32}',row[key])):raise ValueError('Неверная ссылка на запись памяти')
    if total>48_000_000:raise ValueError('Память слишком большая для одного импорта: максимум 48 млн символов')
    positions=set()
    for row in data['chunks']:
        if row['document_id'] not in ids['documents']:raise ValueError('Фрагмент ссылается на отсутствующий документ')
        pair=(row['document_id'],row['position'])
        if pair in positions:raise ValueError('Повторяющийся фрагмент документа')
        positions.add(pair)
    for row in data['learning_sources']:
        if row['document_id'] and row['document_id'] not in ids['documents']:raise ValueError('Источник ссылается на отсутствующий документ')
        if row['memory_id'] and row['memory_id'] not in ids['memories']:raise ValueError('Источник ссылается на отсутствующую память')
        if row['job_id'] is not None and (not isinstance(row['job_id'],str) or not re.fullmatch('[a-f0-9]{32}',row['job_id'])):raise ValueError('Неверная ссылка на изучение')
    return data

def import_memory(store,bundle):
    data=validate_bundle(bundle)
    backup=store.path.parent/'backups'/('before-memory-import-'+new_id()+'.sqlite3');backup.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(store.path)) as source,closing(sqlite3.connect(backup)) as destination:source.backup(destination)
    added={t:0 for t in TABLES};mapping={t:{} for t in TABLES};skipped=0
    chunks_by_doc={r['id']:[] for r in data['documents']}
    for row in sorted(data['chunks'],key=lambda r:r['position']):chunks_by_doc[row['document_id']].append(row)
    def doc_digest(name,rows):return checksum({'name':name,'parts':[(r['position'],r['content']) for r in rows]})
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        existing_notes={(r['scope'],r['content'],r['source']):r['id'] for r in db.execute('SELECT * FROM memories')}
        for row in data['memories']:
            key=(row['scope'],row['content'],row['source']);ident=existing_notes.get(key)
            if ident:skipped+=1
            else:
                ident=new_id();db.execute('INSERT INTO memories VALUES(?,?,?,?,?)',(ident,row['scope'],row['content'],row['created'],row['source']));added['memories']+=1;existing_notes[key]=ident
            mapping['memories'][row['id']]=ident
        existing_docs={}
        for doc in db.execute('SELECT * FROM documents').fetchall():
            parts=db.execute('SELECT position,content FROM chunks WHERE document_id=? ORDER BY position',(doc['id'],)).fetchall()
            existing_docs[doc_digest(doc['name'],parts)]=doc['id']
        for row in data['documents']:
            parts=chunks_by_doc[row['id']];fingerprint=doc_digest(row['name'],parts);ident=existing_docs.get(fingerprint)
            if ident:skipped+=1
            else:
                ident=new_id();db.execute('INSERT INTO documents VALUES(?,?,?)',(ident,row['name'],row['created']));added['documents']+=1;existing_docs[fingerprint]=ident
                for part in parts:
                    cid=new_id();db.execute('INSERT INTO chunks VALUES(?,?,?,?,?,?)',(cid,ident,part['position'],part['content'],None,None))
                    db.execute('INSERT INTO chunk_search VALUES(?,?)',(cid,part['content']));added['chunks']+=1
            mapping['documents'][row['id']]=ident
        existing_sources={(r['url'],r['summary']):r['id'] for r in db.execute('SELECT * FROM learning_sources')}
        imported_job=None
        for row in data['learning_sources']:
            key=(row['url'],row['summary'])
            if key in existing_sources:skipped+=1;continue
            if imported_job is None:
                imported_job=new_id();now=time.time()
                db.execute('INSERT INTO learning_jobs VALUES(?,?,?,?,?,?,?,?,?)',(imported_job,'Материалы из перенесённой памяти','imported','Конспекты и источники восстановлены из файла',0,len(data['learning_sources']),now,now,''))
            ident=new_id();db.execute('INSERT INTO learning_sources VALUES(?,?,?,?,?,?,?,?,?)',(ident,imported_job,row['url'],row['title'],row['summary'],row['method'],mapping['documents'].get(row['document_id']),mapping['memories'].get(row['memory_id']),row['created']))
            existing_sources[key]=ident;added['learning_sources']+=1
        db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('memory_enabled','true'))
        db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('rag_enabled','true'))
    store.audit('memory_import',json.dumps(added))
    return {'added':added,'duplicates_skipped':skipped,'backup':str(backup)}
