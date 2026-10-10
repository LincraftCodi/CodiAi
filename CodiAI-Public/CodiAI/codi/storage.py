"""SQLite persistence; each operation has its own connection and transaction."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from .config import DEFAULTS
from .answers import visible_answer

def new_id() -> str:
    return uuid.uuid4().hex

class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "codi.sqlite3"
        with self.db() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS modes(id TEXT PRIMARY KEY, name TEXT NOT NULL, instruction TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS chats(id TEXT PRIMARY KEY,title TEXT NOT NULL,mode TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,paused INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,role TEXT NOT NULL,content TEXT NOT NULL,status TEXT NOT NULL,created REAL NOT NULL,metadata TEXT DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,scope TEXT NOT NULL,content TEXT NOT NULL,created REAL NOT NULL,source TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,name TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY,document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,position INTEGER NOT NULL,content TEXT NOT NULL,embedding TEXT,embedding_model TEXT);
            CREATE VIRTUAL TABLE IF NOT EXISTS chunk_search USING fts5(chunk_id UNINDEXED,content,tokenize='unicode61');
            CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY,workspace TEXT NOT NULL,path TEXT NOT NULL,old_hash TEXT NOT NULL,content TEXT NOT NULL,diff TEXT NOT NULL,status TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY,action TEXT NOT NULL,detail TEXT NOT NULL,created REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS messages_chat ON messages(chat_id,created);
            CREATE TABLE IF NOT EXISTS images(id TEXT PRIMARY KEY,name TEXT NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS revisions(id TEXT PRIMARY KEY,chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,snapshot TEXT NOT NULL,created REAL NOT NULL);
            """)
            if 'pinned' not in {r['name'] for r in db.execute('PRAGMA table_info(chats)')}:
                db.execute('ALTER TABLE chats ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0')
            # An interrupted process must not leave messages falsely marked as running.
            db.execute("UPDATE messages SET status='interrupted' WHERE status='streaming'")

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def settings(self):
        with self.db() as db:
            return {**DEFAULTS, **{r["key"]: json.loads(r["value"]) for r in db.execute("SELECT * FROM settings")}}

    def save_settings(self, settings):
        with self.db() as db:
            db.executemany("INSERT OR REPLACE INTO settings VALUES(?,?)", [(k, json.dumps(v, ensure_ascii=False)) for k, v in settings.items()])

    def chats(self):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM chats WHERE EXISTS (SELECT 1 FROM messages WHERE chat_id=chats.id) ORDER BY pinned DESC,updated DESC,created DESC,id")]

    def edit_message(self, chat_id, message_id, content):
        if not isinstance(content, str) or not 1 <= len(content.strip()) <= 16000:
            raise ValueError('Сообщение: от 1 до 16000 символов')
        chat = self.chat(chat_id)
        position = next((i for i,m in enumerate(chat['messages']) if m['id']==message_id and m['role']=='user'), None)
        if position is None:
            raise ValueError('Сообщение пользователя не найдено')
        with self.db() as db:
            db.execute('INSERT INTO revisions VALUES(?,?,?,?)', (new_id(),chat_id,json.dumps(chat,ensure_ascii=False),time.time()))
            db.executemany('DELETE FROM messages WHERE id=?', [(m['id'],) for m in chat['messages'][position+1:]])
            metadata=dict(chat['messages'][position]['metadata']);metadata.pop('vision',None);metadata.pop('vision_final',None)
            db.execute('UPDATE messages SET content=?,metadata=? WHERE id=?', (content.strip(),json.dumps(metadata,ensure_ascii=False),message_id))
            first = next(m for m in chat['messages'] if m['role']=='user')
            title = content.strip()[:65] if first['id']==message_id else chat['title']
            db.execute('UPDATE chats SET title=?,updated=? WHERE id=?', (title,time.time(),chat_id))
        return self.chat(chat_id)

    def restore_revision(self, chat_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM revisions WHERE chat_id=? ORDER BY created DESC,rowid DESC LIMIT 1', (chat_id,)).fetchone()
            if not row:
                raise ValueError('Нет предыдущей версии')
            snapshot = json.loads(row['snapshot'])
            db.execute('DELETE FROM messages WHERE chat_id=?', (chat_id,))
            db.executemany('INSERT INTO messages VALUES(?,?,?,?,?,?,?)', [(m['id'],chat_id,m['role'],m['content'],m['status'],m['created'],json.dumps(m['metadata'],ensure_ascii=False)) for m in snapshot['messages']])
            db.execute('UPDATE chats SET title=?,updated=? WHERE id=?', (snapshot['title'],time.time(),chat_id))
            db.execute('DELETE FROM revisions WHERE id=?', (row['id'],))
        return self.chat(chat_id)

    def create_chat(self, mode):
        ident, now = new_id(), time.time()
        with self.db() as db:
            db.execute("INSERT INTO chats(id,title,mode,created,updated) VALUES(?,?,?,?,?)", (ident, "Новый разговор", mode, now, now))
        return self.chat(ident)

    def chat(self, ident):
        with self.db() as db:
            row = db.execute("SELECT * FROM chats WHERE id=?", (ident,)).fetchone()
            if not row:
                raise ValueError("Разговор не найден")
            messages = [dict(r) | {"metadata": json.loads(r["metadata"])} for r in db.execute("SELECT * FROM messages WHERE chat_id=? ORDER BY created,rowid", (ident,))]
            for message in messages:
                if message['role']=='assistant':
                    message['content']=visible_answer(message['content'])
            has_revision = db.execute('SELECT 1 FROM revisions WHERE chat_id=? LIMIT 1',(ident,)).fetchone() is not None
            return {**dict(row), 'has_revision':has_revision, 'messages':messages}

    def add_message(self, chat_id, role, content, status="complete", metadata=None):
        ident, now = new_id(), time.time()
        with self.db() as db:
            db.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?)", (ident, chat_id, role, content, status, now, json.dumps(metadata or {}, ensure_ascii=False)))
            db.execute("UPDATE chats SET updated=? WHERE id=?", (now, chat_id))
            if role == "user":
                db.execute("UPDATE chats SET title=? WHERE id=? AND title='Новый разговор'", (content[:65], chat_id))
        return ident

    def update_message(self, ident, content, status, metadata=None):
        with self.db() as db:
            db.execute("UPDATE messages SET content=?,status=?,metadata=? WHERE id=?", (content, status, json.dumps(metadata or {}, ensure_ascii=False), ident))

    def memories(self, scope=None):
        with self.db() as db:
            if scope:
                rows = db.execute("SELECT * FROM memories WHERE scope IN ('preferences',?) ORDER BY created DESC LIMIT 30", (scope,))
            else:
                rows = db.execute("SELECT * FROM memories ORDER BY created DESC")
            return [dict(r) for r in rows]

    def relevant_memories(self,scope,query,limit=8):
        import re
        words=list(dict.fromkeys(w[:6] for w in re.findall(r'\w+',query.lower()) if len(w)>3))[:12]
        with self.db() as db:
            items=[dict(r) for r in db.execute("SELECT * FROM memories WHERE scope IN ('preferences',?) ORDER BY created DESC LIMIT 200",(scope,))]
            if words:
                # Search all matching records before applying a recency limit.
                db.create_function('codi_fold',1,str.casefold)
                conditions=' OR '.join("codi_fold(content) LIKE ? ESCAPE '\\'" for _ in words)
                patterns=['%'+w.replace('\\','\\\\').replace('_','\\_').replace('%','\\%')+'%' for w in words]
                matches=[dict(r) for r in db.execute("SELECT * FROM memories WHERE scope IN ('preferences',?) AND ("+conditions+") ORDER BY created DESC LIMIT 200",(scope,*patterns))]
                items=list({item['id']:item for item in items+matches}.values())
        items.sort(key=lambda item:(sum(word in item['content'].lower() for word in words),item['created']),reverse=True)
        return [{**item,'content':item['content'][:1200]} for item in items[:limit]]

    def audit(self, action, detail):
        with self.db() as db:
            db.execute("INSERT INTO audit VALUES(?,?,?,?)", (new_id(), action, str(detail)[:3000], time.time()))

    def export(self):
        with self.db() as db:
            result = {table: [dict(r) for r in db.execute(f"SELECT * FROM {table}")] for table in ("modes", "chats", "messages", "memories", "documents", "chunks", "proposals", "audit", "revisions", "images")}
        result["settings"] = self.settings()
        result["format"] = "CodiAI-export-v1"
        return result
