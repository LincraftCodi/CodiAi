"""CodiAI local HTTP application. Python 3.12+, stdlib HTTP/SQLite and Pillow images."""
import argparse
import json
import mimetypes
import os
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
from pathlib import Path
from codi.config import DATA, ROOT, TIERS, WEB, validate_settings
from codi.engine import Engine
from codi.knowledge import Knowledge
from codi.llm import Ollama
from codi.storage import Store, new_id
from codi.tools import Tools
from codi.images import Images, VISION_MODEL
from codi.folders import FolderPicker
from codi.desktop import Desktop
from codi.voice import Voice
from codi.game import Game
from codi.browser import Browser
from codi.learning import Learning
from codi.web_sources import read_source,search
from codi.memory_bundle import export_memory,import_memory

class Application:
    def __init__(self, data=DATA, llm=None):
        self.store = Store(data)
        self.llm = llm or Ollama()
        self.knowledge = Knowledge(self.store, self.llm)
        self.tools = Tools(self.store, self.knowledge, data / "backups")
        self.images = Images(self.store,data/'attachments')
        self.folders = FolderPicker()
        self.desktop=Desktop(self.store,self.images)
        self.voice=Voice()
        if llm is None and os.name=='nt':threading.Thread(target=self.desktop.apps,daemon=True).start()
        self.tools.desktop=self.desktop
        self.engine = Engine(self.store, self.llm, self.knowledge, self.tools,self.images)
        self.game=Game(self.engine,self.images,self.knowledge,self.store)
        self.desktop.game=self.game
        self.browser=Browser()
        self.learning=Learning(self.store,self.llm,self.knowledge,self.engine,self.browser)
        self.token = secrets.token_urlsafe(32)
        self.pulls = {}
        self.pull_lock = threading.Lock()

    def status(self):
        try:
            installed = self.llm.tags()
            online, error = True, None
        except RuntimeError as exc:
            installed, online, error = [], False, str(exc)
        checks={m['name']:self.llm.model_state(m['name']) if hasattr(self.llm,'model_state') else {'installed':True,'reason':'Модель есть в движке'} for m in installed}
        names = {name for name,check in checks.items() if check['installed']}
        return {"version": "0.8.7", "compute": "cpu_only", "cpu_threads": 6, "ollama_online": online, "error": error, "installed": installed,
                "models": [{**t, "installed": t["backend"] in names, "verification": checks.get(t["backend"],{"reason":"Не скачана"})["reason"], "license": "Apache-2.0", "weights": "Qwen3, не собственное обучение CodiAI"} for t in TIERS],
                "embedding_ready": "embeddinggemma:latest" in names, "local_only": True,"vision_ready":VISION_MODEL in names,"vision_verification":checks.get(VISION_MODEL,{"reason":"Не скачана"})["reason"],
                "capabilities": {"chat": "ready" if online and self.store.settings()["model"] in names else "unavailable", "history": "ready", "modes": "ready", "memory": "ready", "documents": "ready", "semantic_rag": "ready" if "embeddinggemma:latest" in names else "unavailable", "project_tools": "ready", "file_diff_backup_undo": "ready", "terminal_sandbox": "planned", "web_search": "ready", "browser": "ready", "web_learning": "ready", "memory_transfer": "ready", "video_transcripts": "ready", "voice": "ready", "vision": "ready" if VISION_MODEL in names else "unavailable", "image_generation": "planned", "video": "planned", "floating_desktop": "ready" if os.name=="nt" else "unavailable", "training": "planned"}}

    def start_pull(self, model):
        if model not in [t["backend"] for t in TIERS] + ["embeddinggemma",VISION_MODEL]:
            raise ValueError("Модель отсутствует в локальном каталоге")
        with self.pull_lock:
            if any(v["state"] == "running" for v in self.pulls.values()):
                raise ValueError("Загрузка модели уже выполняется")
            ident = new_id()
            self.pulls[ident] = {"id": ident, "model": model, "state": "running", "status": "Подготовка", "completed": 0, "total": 0}
        def run():
            try:
                for row in self.llm.pull(model):
                    with self.pull_lock:
                        self.pulls[ident].update(row)
                models=self.llm.tags(refresh=True) if hasattr(self.llm,'model_state') else self.llm.tags()
                expected=model if ':' in model else model+':latest'
                if not any(m['name']==expected for m in models):raise RuntimeError('Загрузка закончилась без установленной модели; повторите скачивание')
                if hasattr(self.llm,'model_state') and not self.llm.model_state(expected)['installed']:raise RuntimeError(self.llm.model_state(expected)['reason'])
                with self.pull_lock:self.pulls[ident]['state']='complete' 
            except (RuntimeError, OSError, ValueError) as exc:
                with self.pull_lock:
                    self.pulls[ident].update(state="error", error=str(exc))
        threading.Thread(target=run, daemon=True).start()
        return {"id": ident}

class Handler(BaseHTTPRequestHandler):
    server_version = "CodiAI/0.1"

    @property
    def app(self):
        return self.server.app

    def log_message(self, format, *args):
        # Request contents and user data are never logged.
        return

    def secure_request(self, mutation=False):
        host = self.headers.get("Host", "")
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if host not in allowed:
            raise PermissionError("Недопустимый Host")
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://" + h for h in allowed}:
            raise PermissionError("Запрос с другого сайта запрещён")
        if mutation and not secrets.compare_digest(self.headers.get("X-Codi-Token", ""), self.app.token):
            raise PermissionError("Недействительный токен локальной сессии")

    def json_response(self, data, status=200):
        content = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def body(self):
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            raise ValueError("Ожидается application/json")
        size = int(self.headers.get("Content-Length", "0"))
        limit=64_000_000 if urlsplit(self.path).path=='/api/memory/import' else 8_000_000
        if size < 0 or size > limit:
            raise ValueError("Слишком большой запрос")
        result = json.loads(self.rfile.read(size) or b"{}")
        if not isinstance(result, dict):
            raise ValueError("Ожидается JSON-объект")
        return result

    def do_GET(self):
        try:
            self.secure_request()
            path = urlsplit(self.path).path
            if path == "/api/bootstrap":
                return self.json_response({"token": self.app.token, "settings": self.app.store.settings(), "modes": self.app.engine.modes(), "chats": self.app.store.chats()})
            if path == "/api/status":
                return self.json_response(self.app.status())
            if path=='/api/game/windows':return self.json_response(self.app.game.available())
            if path=='/api/game':return self.json_response(self.app.game.status())
            if path=='/api/voice/devices':return self.json_response(self.app.voice.devices())
            if path=='/api/voice':return self.json_response(self.app.voice.status())
            if path=='/api/learn':return self.json_response(self.app.learning.jobs())
            if path.startswith('/api/learn/'):return self.json_response(self.app.learning.get(path.rsplit('/',1)[1]))
            if path=='/api/memory/export':return self.json_response(export_memory(self.app.store))
            if path=='/api/memory/list':
                query=parse_qs(urlsplit(self.path).query);needle=query.get('q',[''])[0][:300];offset=max(0,int(query.get('offset',['0'])[0]));limit=50
                with self.app.store.db() as db:
                    total=db.execute('SELECT count(*) FROM memories WHERE content LIKE ?',('%'+needle+'%',)).fetchone()[0]
                    items=[dict(r) for r in db.execute('SELECT * FROM memories WHERE content LIKE ? ORDER BY created DESC LIMIT ? OFFSET ?',('%'+needle+'%',limit,offset))]
                return self.json_response({'items':items,'total':total,'offset':offset})
            if path=='/api/browser/state':return self.json_response(self.app.browser.state())
            if path=='/api/desktop/apps':
                return self.json_response(self.app.desktop.apps())
            if path.startswith('/api/images/'):
                content=self.app.images.bytes(path.rsplit('/',1)[1])
                self.send_response(200)
                self.send_header('Content-Type','image/jpeg')
                self.send_header('Content-Length',str(len(content)))
                self.send_header('X-Content-Type-Options','nosniff')
                self.end_headers();self.wfile.write(content);return
            if path == "/api/chats":
                return self.json_response(self.app.store.chats())
            if path.startswith("/api/chats/"):
                return self.json_response(self.app.store.chat(path.rsplit("/", 1)[1]))
            if path == "/api/memories":
                return self.json_response(self.app.store.memories())
            if path == "/api/documents":
                return self.json_response(self.app.knowledge.list())
            if path == "/api/proposals":
                with self.app.store.db() as db:
                    rows = [dict(r) for r in db.execute("SELECT id,workspace,path,diff,status,created FROM proposals ORDER BY created DESC LIMIT 100")]
                return self.json_response(rows)
            if path == "/api/audit":
                with self.app.store.db() as db:
                    rows = [dict(r) for r in db.execute("SELECT * FROM audit ORDER BY created DESC LIMIT 100")]
                return self.json_response(rows)
            if path == "/api/export":
                return self.json_response(self.app.store.export())
            if path.startswith("/api/pulls/"):
                with self.app.pull_lock:
                    state = self.app.pulls.get(path.rsplit("/", 1)[1])
                    if not state:
                        raise ValueError("Загрузка не найдена")
                    return self.json_response(dict(state))
            if path.startswith("/api/"):
                return self.json_response({"error": "Маршрут не найден"}, 404)
            from urllib.parse import unquote
            file = (WEB / unquote(path).lstrip("/")).resolve() if path != "/" else WEB / "index.html"
            if not file.is_relative_to(WEB.resolve()) or not file.is_file():
                return self.json_response({"error": "Файл не найден"}, 404)
            content = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(file)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(content)
        except PermissionError as exc:
            self.json_response({"error": str(exc)}, 403)
        except (ValueError, OSError) as exc:
            self.json_response({"error": str(exc)}, 400)

    def do_POST(self):
        try:
            self.secure_request(mutation=True)
            data = self.body()
            path = urlsplit(self.path).path
            app = self.app
            if path=='/api/game/start':return self.json_response(app.game.start(data.get('task',''),data.get('window_id')))
            if path=='/api/game/stop':return self.json_response(app.game.stop())
            if path=='/api/voice/start':return self.json_response(app.voice.start(data.get('device')))
            if path=='/api/voice/stop':return self.json_response(app.voice.stop())
            if path=='/api/learn':return self.json_response(app.learning.start(data),201)
            if path=='/api/learn/stop':return self.json_response(app.learning.stop(data['id']))
            if path=='/api/learn/resume':return self.json_response(app.learning.resume(data['id']))
            if path=='/api/learn/delete':return self.json_response(app.learning.delete(data['id']))
            if path=='/api/memory/import':return self.json_response(import_memory(app.store,data))
            if path=='/api/browser/read':return self.json_response(read_source(data.get('url','')))
            if path=='/api/browser/search':return self.json_response(search(data.get('topic','')[:500]))
            if path=='/api/browser/open':return self.json_response(app.browser.open(data.get('url','https://duckduckgo.com/')))
            if path=='/api/browser/heartbeat':return self.json_response(app.browser.heartbeat(data.get('url','')))
            if path == '/api/widget/start':
                if os.name!='nt':raise ValueError('Помощник рабочего стола доступен в Windows')
                subprocess.Popen([str(Path(sys.executable).with_name('pythonw.exe')),str(ROOT/'widget.py')],cwd=ROOT,creationflags=subprocess.CREATE_NO_WINDOW)
                return self.json_response({'started':True})
            if path == '/api/images':
                return self.json_response(app.images.add(data.get('name',''),data.get('data','')),201)
            if path == '/api/workspace/pick':
                result=app.folders.choose(app.store.settings()['workspace'])
                if not result['cancelled']:
                    settings=validate_settings(app.store.settings(),{'workspace':result['path'],'tools_enabled':True},app.engine.modes())
                    app.store.save_settings(settings)
                    result['settings']=settings
                return self.json_response(result)
            if path == "/api/settings":
                settings = validate_settings(app.store.settings(), data, app.engine.modes())
                app.store.save_settings(settings)
                return self.json_response(settings)
            if path == "/api/chats":
                mode = data.get("mode", app.store.settings()["mode"])
                if mode not in app.engine.modes():
                    raise ValueError("Неизвестный режим")
                return self.json_response(app.store.create_chat(mode), 201)
            if path == "/api/chats/delete":
                ident = data["id"]
                with app.engine.lock:
                    if ident in app.engine.active:
                        raise ValueError("Сначала остановите генерацию")
                    with app.store.db() as db:
                        db.execute("DELETE FROM chats WHERE id=?", (ident,))
                        db.execute("DELETE FROM memories WHERE scope IN (?,?)", ("story:"+ident, "chat:"+ident))
                return self.json_response({"deleted": True})
            if path in ('/api/chats/pin','/api/messages/edit','/api/messages/restore'):
                ident = data['chat_id']
                with app.engine.lock:
                    if ident in app.engine.active:
                        raise ValueError('Сначала остановите ответ')
                    app.store.chat(ident)
                    if path == '/api/chats/pin':
                        if type(data.get('pinned')) is not bool:
                            raise ValueError('Неверное состояние закрепления')
                        with app.store.db() as db:
                            db.execute('UPDATE chats SET pinned=? WHERE id=?', (int(data['pinned']),ident))
                        result = app.store.chat(ident)
                    elif path == '/api/messages/edit':
                        result = app.store.edit_message(ident,data['message_id'],data['content'])
                    else:
                        result = app.store.restore_revision(ident)
                return self.json_response(result)
            if path == "/api/chats/mode":
                mode, ident = data["mode"], data["id"]
                if mode not in app.engine.modes():
                    raise ValueError("Неизвестный режим")
                with app.engine.lock:
                    if ident in app.engine.active:
                        raise ValueError("Сначала остановите генерацию")
                    with app.store.db() as db:
                        db.execute("UPDATE chats SET mode=? WHERE id=?", (mode, ident))
                return self.json_response(app.store.chat(ident))
            if path == "/api/stop":
                return self.json_response({"stopped": app.engine.stop(data["chat_id"])})
            if path == "/api/chat":
                return self.stream_chat(data)
            if path == "/api/modes":
                name, instruction = data.get("name", ""), data.get("instruction", "")
                if not isinstance(name, str) or not isinstance(instruction, str) or not 1 <= len(name) <= 60 or not 1 <= len(instruction) <= 4000:
                    raise ValueError("Укажите название и инструкцию до 4000 символов")
                ident = "custom_" + new_id()
                with app.store.db() as db:
                    db.execute("INSERT INTO modes VALUES(?,?,?)", (ident, name, instruction))
                return self.json_response(app.engine.modes())
            if path == "/api/memories":
                content, scope = data.get("content", ""), data.get("scope", "preferences")
                if not isinstance(content, str) or not 1 <= len(content) <= 2000:
                    raise ValueError("Память: от 1 до 2000 символов")
                allowed_scopes = {"preferences", "learning"}
                if data.get("chat_id"):
                    allowed_scopes.add(app.engine.scope(app.store.chat(data["chat_id"])))
                if scope not in allowed_scopes:
                    raise ValueError("Недопустимая область памяти")
                import re
                if re.match(r'^(?:изучи|изучить|выучи|исследуй)\s+',content.strip(),re.I) or re.fullmatch(r'https?://\S+',content.strip()):
                    return self.json_response({'study_started':app.learning.start({'topic':content.strip()})},201)
                with app.store.db() as db:
                    db.execute("INSERT INTO memories VALUES(?,?,?,?,?)", (new_id(), scope, content, time.time(), "user"))
                return self.json_response(app.store.memories())
            if path == "/api/memories/delete":
                app.learning.forget(memory_id=data['id'])
                with app.store.db() as db:
                    db.execute("DELETE FROM memories WHERE id=?", (data["id"],))
                return self.json_response({"deleted": True})
            if path == "/api/documents":
                return self.json_response(app.knowledge.add(data.get("name", ""), data.get("text", ""), app.store.settings()["semantic_rag"]))
            if path == "/api/documents/delete":
                app.learning.forget(document_id=data['id'])
                app.knowledge.delete(data["id"])
                return self.json_response({"deleted": True})
            if path == "/api/knowledge/search":
                query = data.get("query", "")
                if not isinstance(query, str) or len(query) > 4000:
                    raise ValueError("Неверный поисковый запрос")
                return self.json_response(app.knowledge.search(query, app.store.settings()["semantic_rag"]))
            if path == "/api/tools":
                return self.json_response(app.tools.execute(data.get("name", ""), data.get("arguments", {}), app.store.settings()))
            if path == "/api/proposals/apply":
                return self.json_response(app.tools.apply(data["id"], app.store.settings()["workspace"]))
            if path == "/api/proposals/undo":
                return self.json_response(app.tools.undo(data["id"], app.store.settings()["workspace"]))
            if path == "/api/models/pull":
                return self.json_response(app.start_pull(data.get("model", "")))
            return self.json_response({"error": "Маршрут не найден"}, 404)
        except PermissionError as exc:
            # Unread POST bytes can reset TCP on Windows before the 403 arrives.
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if 0 < length <= 8_000_000:
                    self.connection.settimeout(3)
                    self.rfile.read(length)
            except (OSError, ValueError):
                pass
            self.json_response({"error": str(exc)}, 403)
        except (ValueError, KeyError, TypeError, OSError, RuntimeError) as exc:
            self.json_response({"error": str(exc)}, 400)

    def stream_chat(self, data):
        app = self.app
        ident = data.get("chat_id", "")
        chat = app.store.chat(ident)
        text = data.get("message", "")
        if not isinstance(text, str) or len(text) > 16000:
            raise ValueError("Сообщение: до 16 000 символов")
        regenerate = data.get("regenerate", False)
        continue_edited = data.get('continue_edited',False)
        image_ids=data.get('images',[])
        if not isinstance(image_ids,list) or len(image_ids)>2:
            raise ValueError('Прикрепите не более двух картинок к одному сообщению')
        attachments=[app.images.get(i) for i in image_ids]
        desktop_context=data.get('desktop_context',{})
        if not isinstance(desktop_context,dict) or set(desktop_context)-{'file','folder'} or any(not isinstance(v,str) or len(v)>2000 for v in desktop_context.values()):
            raise ValueError('Неверный контекст выбранного файла')
        from codi.chat_context import chat_context
        desktop_context=desktop_context or chat_context(chat)
        if type(regenerate) is not bool or type(continue_edited) is not bool or (not regenerate and not continue_edited and not text.strip() and not attachments):
            raise ValueError("Сообщение пустое")
        if continue_edited and (not chat['messages'] or chat['messages'][-1]['role']!='user'):
            raise ValueError('Нет сообщения для нового ответа')
        if regenerate and (not chat["messages"] or chat["messages"][-1]["role"] != "assistant"):
            raise ValueError("Нет ответа для повторной генерации")
        operation = app.engine.reserve(ident)
        try:
            if not regenerate and not continue_edited:
                import re
                study_request=re.match(r'^(?:изучи|выучи|исследуй|научись|найди сайты|найди туториалы|найди руководства)\b',text.strip(),re.I) and chat['mode'] in ('general','teacher','researcher','desktop') and not re.search(r'проект|файл|папк|структур|этот код',text,re.I)
                if study_request:
                    study=app.learning.start({'topic':text})
                    direct={'reply':'Начала изучение: '+study['topic']+'. Прогресс и источники — в разделе «Память». Уже сохранённое можно использовать в чате.','action':None}
                else:direct=app.desktop.command(text,desktop_context,chat)
                search_request=re.fullmatch(r'(?:найди|поищи|ищи)\s+(?:в интернете|в сети)\s+(.+)',text.strip().rstrip('!.').strip(),re.I|re.S)
                if direct is None and search_request and chat['mode']!='super':
                    from codi.web_sources import search
                    hits=search(search_request[1],6,educational=False)
                    reply='Результаты поиска (аннотации поисковика, страницы ещё не проверены):\n\n'+'\n\n'.join('['+item['title'].replace(']','')+']('+item['url']+')\n'+item.get('snippet','') for item in hits) if hits else 'Поиск не вернул результатов или сервис недоступен. Попробуйте другой запрос или прямую ссылку.'
                    direct={'reply':reply,'action':None}
                if direct is not None:
                    app.store.add_message(ident,'user',text,metadata={'desktop_context':desktop_context})
                    app.store.add_message(ident,'assistant',direct['reply'],metadata={'desktop_action':direct.get('action'),'desktop_context':direct.get('context',desktop_context)})
                    if direct.get('action'):app.desktop.record(ident,direct['action'],direct['reply'])
                    app.engine.release(ident)
                    return self.json_response({'command':True,'reply':direct['reply'],'desktop_context':direct.get('context',desktop_context)})
            # Verify model availability before modifying the history.
            names = {m["name"] for m in app.llm.tags()}
            if app.store.settings()["model"] not in names:
                raise ValueError("Модель ещё не установлена. Откройте раздел «Модели»")
            if hasattr(app.llm,'model_state') and not app.llm.model_state(app.store.settings()['model'])['installed']:raise ValueError(app.llm.model_state(app.store.settings()['model'])['reason'])
            if attachments and hasattr(app.llm,'model_state') and not app.llm.model_state(VISION_MODEL)['installed']:raise ValueError(app.llm.model_state(VISION_MODEL)['reason'])
            if attachments and VISION_MODEL not in names:
                raise ValueError('Модель для картинок ещё не установлена. Откройте «Модели» и загрузите анализ изображений')
            if regenerate:
                with app.store.db() as db:
                    db.execute("DELETE FROM messages WHERE id=?", (chat["messages"][-1]["id"],))
            elif not continue_edited:
                if chat["mode"] == "roleplay" and text.strip() in ("/pause", "/resume"):
                    paused = int(text.strip() == "/pause")
                    with app.store.db() as db:
                        db.execute("UPDATE chats SET paused=? WHERE id=?", (paused, ident))
                    app.store.add_message(ident, "user", text)
                    app.store.add_message(ident, "assistant", "Сцена приостановлена." if paused else "Сцена продолжена.")
                    app.engine.release(ident)
                    return self.json_response({"command": True})
                if chat["paused"]:
                    raise ValueError("Сцена приостановлена. Введите /resume")
                app.store.add_message(ident, "user", text or 'Что изображено на картинке?',metadata={'images':attachments,'desktop_context':desktop_context})
        except BaseException:
            app.engine.release(ident)
            raise
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        iterator = app.engine.generate(ident, operation)
        try:
            for event in iterator:
                self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            operation.cancel()
        finally:
            iterator.close()
            app.engine.release(ident)

def make_server(port=8765, app=None):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.app = app or Application()
    server.daemon_threads = True
    return server

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.environ.get("CODIAI_PORT", 8765)))
    args = parser.parse_args()
    server = make_server(args.port)
    def warm_selected_model():
        try:
            settings=server.app.store.settings()
            if server.app.llm.model_state(settings['model'])['installed']:
                server.app.llm.warm(settings['model'],settings['num_ctx'],settings['thinking'])
        except (RuntimeError,OSError,ValueError) as exc:
            print('Предзагрузка модели не завершена: '+str(exc),flush=True)
    threading.Thread(target=warm_selected_model,daemon=True).start()
    print(f"CodiAI: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.app.voice.stop();server.app.game.stop()
        for operation in list(server.app.engine.active.values()):
            operation.cancel()
    finally:
        server.server_close()
