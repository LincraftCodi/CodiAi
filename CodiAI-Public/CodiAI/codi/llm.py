"""Local Ollama adapter; no external AI calls, API keys or cloud models."""
import json
import http.client
import socket
import threading
import time
from pathlib import Path
from .config import ROOT
from .model_inventory import local_state
from .context_budget import ContextOverflow,model_error,prepare,recover
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from .config import OLLAMA

class Ollama:
    def __init__(self, base=OLLAMA):
        self.base = base
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.prepared = {}
        self.prepare_lock = threading.Lock()
        self.transport_context=threading.local()
        self.tags_cache=None;self.tags_time=0;self.tags_lock=threading.Lock()
        self.compute={'num_thread':6,'num_batch':256}

    def prepare_model(self, model, thinking=False):
        """Fix Qwen3's legacy unconditional thinking prefill, sharing its weights."""
        if not model.startswith("qwen3:") or model.endswith('-instruct') or thinking:
            return model
        with self.prepare_lock:
            if model in self.prepared:
                return self.prepared[model]
            with self.request("/api/show", {"model": model}) as response:
                info = json.load(response)
            template = info["template"]
            needle = "<think>\n{{ end }}"
            if needle not in template:
                self.prepared[model] = model
                return model
            # The ggml runner does not consistently populate Go .Think flags.
            # A separate fast template closes the prefill unconditionally.
            fixed = template.replace(needle, "<think>\n\n</think>\n\n{{ end }}")
            alias = "codi-qwen3-" + model.split(":", 1)[1] + "-fast-v2"
            with self.request("/api/create", {"model": alias, "from": model, "template": fixed, "stream": False}, timeout=30) as response:
                result = json.load(response)
            if result.get("status") != "success":
                raise RuntimeError("Не удалось подготовить шаблон локальной модели")
            self.prepared[model] = alias
            return alias

    def request(self, path, payload=None, timeout=10):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            operation=getattr(self.transport_context,'operation',None)
            if operation is not None and path=='/api/chat':
                target=urlsplit(self.base)
                connection=(http.client.HTTPSConnection if target.scheme=='https' else http.client.HTTPConnection)(target.hostname,target.port,timeout=timeout)
                operation.connection=connection;connection.connect();operation.socket=connection.sock
                # Bound connecting, but wait for generation until Stop closes the socket.
                connection.sock.settimeout(None)
                if operation.cancelled.is_set():raise ConnectionError('Остановлено')
                connection.request('POST',target.path.rstrip('/')+path,body=data,headers={'Content-Type':'application/json'})
                response=connection.getresponse()
                if response.status!=200:
                    try:detail=json.loads(response.read()).get('error','HTTP '+str(response.status))
                    except ValueError:detail='HTTP '+str(response.status)
                    response.close();raise model_error(detail)
                return response
            return self.opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read()).get("error", str(exc))
            except (ValueError, AttributeError):
                detail = str(exc)
            raise model_error(detail) from exc
        except (urllib.error.URLError, OSError) as exc:
            if getattr(self.transport_context,'operation',None) is not None and self.transport_context.operation.cancelled.is_set():raise RuntimeError('Остановлено') from exc
            raise RuntimeError("Локальный движок Ollama недоступен. Запустите Start-CodiAI.cmd или установите Ollama.") from exc

    def tags(self,refresh=False):
        with self.tags_lock:
            if not refresh and self.tags_cache is not None and time.monotonic()-self.tags_time<4:return self.tags_cache
            with self.request('/api/tags',timeout=3) as response:models=json.load(response).get('models',[])
            found={}
            for model in models:
                if model['name'] not in found:found[model['name']]=model
            self.tags_cache=list(found.values());self.tags_time=time.monotonic();return self.tags_cache

    def model_state(self,name):return local_state(ROOT/'runtime/models',name)

    def warm(self,model,num_ctx=4096,thinking=False):
        model=self.prepare_model(model,thinking)
        with self.request('/api/generate',{'model':model,'prompt':'','stream':False,'keep_alive':'15m','options':{'num_gpu':0,'num_ctx':num_ctx,**self.compute}},timeout=90) as response:
            result=json.load(response)
        if not result.get('done'):raise RuntimeError('Модель не завершила загрузку')
        return result


    def stream(self, payload, operation):
        # GPU use is disabled following the recorded CUDA/TDR crash on this PC.
        payload = {**payload, "model": self.prepare_model(payload["model"],payload.get('think',False)), "options": {**payload.get("options", {}), "num_gpu": 0, "num_predict": -1, **self.compute}, "keep_alive": "90s" if payload['model'].startswith('qwen3-vl:') else "15m"}
        payload=prepare(payload)
        self.transport_context.operation=operation
        try:
            for attempt in range(6):
                response=None;emitted=False
                if operation.cancelled.is_set():return
                try:
                    response=self.request('/api/chat',payload,timeout=10)
                    operation.response=response
                    while not operation.cancelled.is_set():
                        line=response.readline()
                        if not line:break
                        row=json.loads(line)
                        if row.get('error'):raise model_error(row['error'])
                        emitted=True;yield row
                        if row.get('done'):break
                    return
                except ContextOverflow as exc:
                    if operation.cancelled.is_set():return
                    replacement=None if emitted or operation.cancelled.is_set() or attempt==5 else recover(payload,exc)
                    if replacement is None:raise RuntimeError('Запрос слишком велик для локальной модели даже после сокращения старого контекста. История сохранена; разделите задачу на части.') from exc
                    payload=replacement
                finally:
                    operation.response=None
                    if response:response.close()
                    if operation.connection:operation.connection.close()
                    operation.connection=None;operation.socket=None
        finally:self.transport_context.operation=None

    def embed(self, texts, model="embeddinggemma"):
        with self.request("/api/embed", {"model": model, "input": texts, "truncate": False, "keep_alive": "0s", "options": {"num_gpu": 0, "num_thread": 2, "num_batch": 32}}, timeout=180) as response:
            embeddings = json.load(response)["embeddings"]
        if len(embeddings) != len(texts):
            raise RuntimeError("Некорректный ответ embedding-модели")
        return embeddings

    def pull(self, model):
        with self.request("/api/pull", {"model": model, "stream": True}, timeout=600) as response:
            for line in response:
                row = json.loads(line)
                if row.get("error"):
                    raise RuntimeError(row["error"])
                yield row
