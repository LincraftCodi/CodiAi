import http.client
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from codi.config import ROOT, validate_settings
from codi.engine import Operation
from codi.llm import Ollama
from codi.tools import calculator, safe_path
from server import Application, make_server

TEMP = ROOT / "runtime" / "temp"
TEMP.mkdir(parents=True, exist_ok=True)

class FakeLLM:
    """Deterministic transport substitute; live-model validation is separate."""
    def __init__(self):
        self.payloads = []
        self.calls = 0
        self.use_tool = False
        self.truncate = False

    def tags(self):
        return [{"name": "qwen3:4b-instruct"}, {"name": "qwen3:1.7b"}, {"name": "embeddinggemma:latest"}]

    def embed(self, texts, model="embeddinggemma"):
        return [[float("синий" in t.lower()), float("красный" in t.lower()), 0.1] for t in texts]

    def stream(self, payload, operation):
        self.payloads.append(payload)
        self.calls += 1
        if self.use_tool and self.calls == 1:
            yield {"message": {"tool_calls": [{"function": {"name": "calculator", "arguments": {"expression": "21*2"}}}]}, "done": True}
        else:
            yield {"message": {"content": "Ответ "}}
            if not self.truncate:
                yield {"message": {"content": "42"}, "done": True}

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=TEMP)
        self.root = Path(self.temp.name)
        self.llm = FakeLLM()
        self.app = Application(self.root / "data", self.llm)
        self.workspace = self.root / "project"
        self.workspace.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def settings(self, **patch):
        result = validate_settings(self.app.store.settings(), patch, self.app.engine.modes())
        self.app.store.save_settings(result)
        return result

    def test_settings_validation_and_persistence(self):
        self.settings(theme="rose", name="Помощник")
        self.assertEqual(self.app.store.settings()["theme"], "rose")
        for patch in ({"temperature": True}, {"theme": "unknown"}, {"model": "cloud:latest"}, {"num_ctx": 1}, {"workspace": self.workspace.anchor}, {"animations": "yes"}):
            with self.assertRaises((ValueError, OSError)):
                self.settings(**patch)
        self.assertEqual(self.app.store.settings()["name"], "Помощник")

    def test_history_persists_and_deletes(self):
        chat = self.app.store.create_chat("teacher")
        self.app.store.add_message(chat["id"], "user", "Привет")
        self.assertEqual(self.app.store.chat(chat["id"])["title"], "Привет")
        with self.app.store.db() as db:
            db.execute("DELETE FROM chats WHERE id=?", (chat["id"],))
            self.assertEqual(db.execute("SELECT count(*) FROM messages").fetchone()[0], 0)

    def test_calculator_cannot_execute_code(self):
        self.assertEqual(calculator("(20+1)*2"), 42)
        for expression in ("__import__('os').system('whoami')", "2**999999", "1/0", "True", "1e300", "[1]*100"):
            with self.assertRaises((ValueError, ArithmeticError)):
                calculator(expression)

    def test_path_boundary_and_secret_exclusion(self):
        for relative in ("../outside.py", "D:/outside.py", ".env", ".git/config", "file.py:stream", "node_modules/x.js", "id_rsa.txt"):
            with self.assertRaises(ValueError):
                safe_path(str(self.workspace), relative)
        self.assertEqual(safe_path(str(self.workspace), "nested/main.py"), self.workspace / "nested/main.py")

    def test_proposal_requires_apply_and_supports_undo(self):
        target = self.workspace / "main.py"
        target.write_bytes(b"old = 1\r\n")
        settings = self.settings(workspace=str(self.workspace), tools_enabled=True)
        result = self.app.tools.execute("propose_write", {"path": "main.py", "content": "new = 2\n"}, settings)
        self.assertEqual(target.read_bytes(), b"old = 1\r\n")
        self.app.tools.apply(result["proposal_id"], str(self.workspace))
        self.assertEqual(target.read_bytes(), b"new = 2\n")
        with self.assertRaises(ValueError):
            self.app.tools.apply(result["proposal_id"], str(self.workspace))
        self.app.tools.undo(result["proposal_id"], str(self.workspace))
        self.assertEqual(target.read_bytes(), b"old = 1\r\n")

    def test_proposal_conflicts_and_changed_workspace(self):
        target = self.workspace / "main.py"
        target.write_text("first", encoding="utf-8")
        settings = self.settings(workspace=str(self.workspace), tools_enabled=True)
        result = self.app.tools.execute("propose_write", {"path": "main.py", "content": "second"}, settings)
        target.write_text("edited elsewhere", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.app.tools.apply(result["proposal_id"], str(self.workspace))
        with self.assertRaises(ValueError):
            self.app.tools.apply(result["proposal_id"], str(self.root))
        self.assertEqual(target.read_text(), "edited elsewhere")

    def test_new_file_undo(self):
        settings = self.settings(workspace=str(self.workspace), tools_enabled=True)
        result = self.app.tools.execute("propose_write", {"path": "new.py", "content": "print(42)"}, settings)
        self.app.tools.apply(result["proposal_id"], str(self.workspace))
        self.app.tools.undo(result["proposal_id"], str(self.workspace))
        self.assertFalse((self.workspace / "new.py").exists())

    def test_disabled_and_unknown_tools(self):
        with self.assertRaises(ValueError):
            self.app.tools.execute("calculator", {"expression": "2+2"}, self.app.store.settings())
        settings = self.settings(tools_enabled=True)
        with self.assertRaises(ValueError):
            self.app.tools.execute("shell", {"command": "whoami"}, settings)

    def test_document_search_and_deletion(self):
        document = self.app.knowledge.add("Палитра.txt", "Наш персонаж синий, он любит программирование.")
        result = self.app.knowledge.search("программирование")
        self.assertEqual(result[0]["name"], "Палитра.txt")
        self.app.knowledge.delete(document["id"])
        self.assertEqual(self.app.knowledge.search("программирование"), [])

    def test_semantic_search_has_source(self):
        self.app.knowledge.add("Синий.txt", "Синий персонаж", True)
        self.app.knowledge.add("Красный.txt", "Красный персонаж", True)
        result = self.app.knowledge.search("Синий", True)
        self.assertEqual(result[0]["name"], "Синий.txt")
        self.assertNotIn("embedding", result[0])

    def test_mode_memory_isolation(self):
        story = self.app.store.create_chat("roleplay")
        normal = self.app.store.create_chat("general")
        with self.app.store.db() as db:
            db.execute("INSERT INTO memories VALUES('a',?,'dragon',0,'user')", (self.app.engine.scope(story),))
        self.assertEqual(len(self.app.store.memories(self.app.engine.scope(story))), 1)
        self.assertEqual(len(self.app.store.memories(self.app.engine.scope(normal))), 0)

    def test_stream_persists_complete_response(self):
        chat = self.app.store.create_chat("teacher")
        self.app.store.add_message(chat["id"], "user", "Объясни")
        events = list(self.app.engine.generate(chat["id"], self.app.engine.reserve(chat["id"])))
        self.assertEqual(events[-1]["status"], "complete")
        self.assertEqual(self.app.store.chat(chat["id"])["messages"][-1]["content"], "Ответ 42")
        self.assertIn("простых примерах", self.llm.payloads[0]["messages"][0]["content"])

    def test_tool_round_trip(self):
        self.settings(tools_enabled=True)
        self.llm.use_tool = True
        chat = self.app.store.create_chat("analyst")
        self.app.store.add_message(chat["id"], "user", "21*2")
        events = list(self.app.engine.generate(chat["id"], self.app.engine.reserve(chat["id"])))
        tool = next(e for e in events if e["type"] == "tool")
        self.assertEqual(tool["result"]["value"], 42)
        self.assertEqual(self.llm.payloads[-1]["messages"][-1]["role"], "tool")

    def test_truncated_stream_is_error(self):
        self.llm.truncate = True
        chat = self.app.store.create_chat("general")
        self.app.store.add_message(chat["id"], "user", "Вопрос")
        events = list(self.app.engine.generate(chat["id"], self.app.engine.reserve(chat["id"])))
        self.assertEqual(events[-1]["status"], "error")
        self.assertFalse(self.app.engine.active)

    def test_cancel_and_single_generation(self):
        chat = self.app.store.create_chat("general")
        operation = self.app.engine.reserve(chat["id"])
        with self.assertRaises(ValueError):
            self.app.engine.reserve("other")
        operation.cancel()
        events = list(self.app.engine.generate(chat["id"], operation))
        self.assertEqual(events[-1]["status"], "stopped")

class HTTPTests(unittest.TestCase):
    def setUp(self):
        CoreTests.setUp(self)
        self.server = make_server(0, self.app)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        CoreTests.tearDown(self)

    def request(self, method, path, data=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        defaults = {"Content-Type": "application/json", "X-Codi-Token": self.app.token}
        defaults.update(headers or {})
        connection.request(method, path, body=json.dumps(data) if data is not None else None, headers=defaults)
        response = connection.getresponse()
        status, content = response.status, response.read()
        connection.close()
        return status, content

    def test_http_session_and_origin_protection(self):
        status, body = self.request("GET", "/api/bootstrap")
        self.assertEqual(status, 200)
        self.assertIn("token", json.loads(body))
        self.assertEqual(self.request("POST", "/api/chats", {}, {"X-Codi-Token": "bad"})[0], 403)
        self.assertEqual(self.request("POST", "/api/chats", {}, {"Origin": "https://attacker.test"})[0], 403)
        self.assertEqual(self.request("GET", "/api/bootstrap", headers={"Host": "attacker.test"})[0], 403)

    def test_http_stream_and_custom_mode(self):
        status, body = self.request("POST", "/api/modes", {"name": "Наставник", "instruction": "Объясняй разработку игр"})
        self.assertEqual(status, 200)
        ident = next(k for k in json.loads(body) if k.startswith("custom_"))
        _, body = self.request("POST", "/api/chats", {"mode": ident})
        chat = json.loads(body)
        status, body = self.request("POST", "/api/chat", {"chat_id": chat["id"], "message": "Привет"})
        events = [json.loads(line) for line in body.splitlines()]
        self.assertEqual(status, 200)
        self.assertEqual(events[-1]["status"], "complete")

    def test_http_edit_continue_restore_and_pin(self):
        _, body = self.request('POST','/api/chats',{'mode':'general'})
        ident = json.loads(body)['id']
        self.request('POST','/api/chat',{'chat_id':ident,'message':'Первый вопрос'})
        _, body = self.request('GET','/api/chats/'+ident)
        message_id=json.loads(body)['messages'][0]['id']
        status,body=self.request('POST','/api/messages/edit',{'chat_id':ident,'message_id':message_id,'content':'Новый вопрос'})
        self.assertEqual(status,200)
        self.assertEqual(len(json.loads(body)['messages']),1)
        status,body=self.request('POST','/api/chat',{'chat_id':ident,'message':'','continue_edited':True})
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body.splitlines()[-1])['status'],'complete')
        _,body=self.request('GET','/api/chats/'+ident)
        self.assertEqual(len(json.loads(body)['messages']),2)
        _,body=self.request('POST','/api/chats/pin',{'chat_id':ident,'pinned':True})
        self.assertTrue(json.loads(body)['pinned'])
        _,body=self.request('POST','/api/messages/restore',{'chat_id':ident})
        self.assertEqual(json.loads(body)['messages'][0]['content'],'Первый вопрос')
        self.assertEqual(self.request('POST','/api/messages/edit',{'chat_id':ident,'message_id':'missing','content':'bad'})[0],400)

class AdapterTests(unittest.TestCase):
    def test_cpu_transport_and_thinking_template(self):
        class Transport(Ollama):
            def __init__(self):
                super().__init__()
                self.requests = []
            def request(self, path, payload=None, timeout=10):
                self.requests.append((path, payload))
                if path == "/api/show":
                    result = {"template": "<think>\n{{ end }}"}
                elif path == "/api/create":
                    result = {"status": "success"}
                else:
                    result = {"message": {"content": "ok"}, "done": True}
                return io.BytesIO((json.dumps(result) + "\n").encode())
        llm = Transport()
        payload = {"model": "qwen3:1.7b", "messages": [], "think": False, "options": {"num_gpu": 100}}
        events = list(llm.stream(payload, Operation()))
        create = next(p for path, p in llm.requests if path == "/api/create")
        self.assertIn('<think>\n\n</think>', create['template'])
        self.assertNotIn('$.Think', create['template'])
        request = llm.requests[-1][1]
        self.assertEqual(request["options"]["num_gpu"], 0)
        self.assertEqual(request["options"]["num_thread"], 6)
        self.assertEqual(request['keep_alive'],'15m')
        self.assertFalse(request["think"])
        self.assertEqual(events[0]["message"]["content"], "ok")
        self.assertEqual(payload["options"]["num_gpu"], 100)

if __name__ == "__main__":
    unittest.main()
