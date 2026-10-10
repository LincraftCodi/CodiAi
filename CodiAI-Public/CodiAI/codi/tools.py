"""Bounded tools and explicit review/apply file edits. Never executes shell code."""
import ast
import difflib
import hashlib
import json
import math
import operator
import os
import shutil
import time
from pathlib import Path
from .storage import new_id
from .asset_checks import check_svg,check_obj

TEXT_SUFFIXES = {".lua", ".luau", ".obj", ".mtl", ".gltf",".txt", ".md", ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".css", ".html", ".yaml", ".yml", ".toml", ".rs", ".go", ".java", ".cpp", ".c", ".h", ".cs", ".sql", ".xml", ".ini", ".cfg", ".sh", ".ps1", ".bat", ".cmd", ".kt", ".kts", ".gradle", ".properties", ".svg", ".vue", ".svelte", ".dart"}
BLOCKED_PARTS = {".git", ".ssh", ".aws", ".azure", "node_modules", ".venv", "venv", "runtime", "__pycache__"}
BINARY_SUFFIXES={'.blend','.glb','.fbx','.apk','.aab','.jar','.exe','.dll','.msi','.zip','.7z','.rar','.png','.jpg','.jpeg','.gif','.webp','.pdf','.docx','.xlsx','.pptx','.mp3','.mp4','.woff','.woff2','.ttf','.sqlite','.sqlite3','.db','.ico'}

def digest(data):
    return hashlib.sha256(data).hexdigest()

def safe_path(workspace, relative, must_exist=False):
    if not workspace:
        raise ValueError("Сначала выберите папку проекта в настройках")
    root = Path(workspace).resolve(strict=True)
    path = Path(relative)
    if '..' in path.parts:raise ValueError('Переход за пределы проекта запрещён')
    if path.is_absolute():
        try:path=path.relative_to(root)
        except ValueError:raise ValueError('Путь находится вне выбранной папки проекта') from None
    if path.drive or ':' in str(path):raise ValueError('Укажите путь внутри выбранной папки проекта')
    for part in path.parts:
        if part.lower() in BLOCKED_PARTS or (part.lower().startswith(".env") and part.lower() not in ('.env.example','.env.sample','.env.template')) or part.endswith((".", " ")):
            raise ValueError("Этот путь исключён из доступа")
    target = root / path
    cursor = target
    while cursor != root:
        if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
            raise ValueError("Ссылки и junction запрещены")
        cursor = cursor.parent
    resolved = target.resolve(strict=must_exist)
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError("Путь должен указывать на файл внутри проекта")
    if resolved.suffix.lower() in BINARY_SUFFIXES:
        raise ValueError("Этот формат двоичный. Для кода и конфигураций создавайте текстовые файлы")
    if resolved.name.lower().startswith(("credentials", "id_rsa", "id_ed25519")):
        raise ValueError("Файл с секретами исключён из доступа")
    return resolved

def calculator(expression):
    if not isinstance(expression, str) or len(expression) > 300:
        raise ValueError("Слишком длинное выражение")
    operations = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow}
    def evaluate(node, depth=0):
        if depth > 15:
            raise ValueError("Слишком сложное выражение")
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand, depth+1) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and type(node.op) in operations:
            left, right = evaluate(node.left, depth+1), evaluate(node.right, depth+1)
            if isinstance(node.op, ast.Pow) and (abs(right) > 12 or abs(left) > 1e6):
                raise ValueError("Слишком большая степень")
            value = operations[type(node.op)](left, right)
        else:
            raise ValueError("Разрешены только числа и арифметические операции")
        if not isinstance(value, (int, float)) or abs(value) > 1e100 or not math.isfinite(value):
            raise ValueError("Результат вне допустимого диапазона")
        return value
    return evaluate(ast.parse(expression, mode="eval").body)

def schema(name, description, properties, required):
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {"type": "object", "properties": {k: {"type": "string", "description": v} for k, v in properties.items()}, "required": required, "additionalProperties": False}}}

DESKTOP_SCHEMAS = [
    schema('ask_user','Уточнить важную неоднозначность. Показать вопрос, варианты и поле своего ответа. После вызова дождись ответа пользователя.',{'question':'Короткий вопрос','choices':'От 2 до 5 коротких вариантов, разделённых переводами строки'},['question','choices']),
    schema("project_build","Запустить сборку или тесты в выбранной папке; выполняет код проекта. APK создаётся настоящей Android-сборкой",{"kind":"android, npm-build, npm-test или python-test"},["kind"]),
    schema('desktop_mkdir','Создать новую папку, в том числе ещё не существующую. Имя — на рабочем столе; полный путь — в указанном месте.',{'name':'Имя папки или полный абсолютный путь новой папки'},['name']),
    schema('desktop_launch','Запустить установленное приложение по имени, не shell-команду',{'name':'Название установленной программы'},['name']),
    schema('desktop_windows','Показать заголовки открытых окон',{},[]),
    schema('desktop_window','Свернуть, развернуть, восстановить или запросить закрытие конкретного окна',{'action':'minimize, maximize, restore или close','query':'Название приложения или полный заголовок окна'},['action','query']),
]
SCHEMAS = DESKTOP_SCHEMAS + [
    schema("calculator", "Вычислить арифметическое выражение", {"expression": "Числа и + - * / % **"}, ["expression"]),
    schema("knowledge_search", "Найти фрагменты загруженных пользователем документов", {"query": "Поисковый запрос"}, ["query"]),
    schema("project_list", "Показать текстовые файлы выбранного проекта", {}, []),
    schema("project_read", "Прочитать текстовый файл выбранного проекта", {"path": "Относительный путь"}, ["path"]),
    schema("project_search", "Найти строку в текстовых файлах выбранного проекта", {"query": "Строка для поиска"}, ["query"]),
    schema("project_check", "Проверить Python/JSON/glTF, структуру SVG или индексы OBJ без исполнения кода", {"path": "Относительный путь .py, .json, .gltf, .svg или .obj"}, ["path"]),
    schema('project_mkdir','Создать папку внутри выбранного проекта',{'path':'Относительный путь папки'},['path']),
    schema("propose_write", "Создать предложение с полным содержимым файла. При включённой автозаписи приложение применяет его и возвращает проверенный полный путь; иначе требуется применение пользователем", {"path": "Относительный путь", "content": "Полный новый текст файла"}, ["path", "content"]),
]

class Tools:
    def __init__(self, store, knowledge, backups):
        self.store, self.knowledge, self.backups = store, knowledge, backups

    def files(self, workspace):
        if not workspace:
            raise ValueError("Выберите папку проекта в настройках")
        root = Path(workspace).resolve(strict=True)
        count = 0
        for folder, directories, files in os.walk(root, followlinks=False):
            directories[:] = [d for d in directories if d.lower() not in BLOCKED_PARTS and not Path(folder, d).is_symlink() and not (hasattr(Path(folder, d), "is_junction") and Path(folder, d).is_junction())]
            for name in files:
                relative = str(Path(folder, name).relative_to(root))
                try:
                    path = safe_path(workspace, relative, True)
                    if not path.is_file() or path.stat().st_size > 200000:continue
                    with path.open('rb') as probe:sample=probe.read(1024)
                    if b'\x00' not in sample:
                        yield relative
                        count += 1
                        if count >= 600:
                            return
                except (ValueError, OSError):
                    continue

    def execute(self, name, arguments, settings):
        if not settings["tools_enabled"] and name!='ask_user':
            raise ValueError("Инструменты отключены")
        definition = next((s["function"] for s in SCHEMAS if s["function"]["name"] == name), None)
        if not definition or not isinstance(arguments, dict):
            raise ValueError("Неизвестный инструмент")
        parameters = definition["parameters"]
        if set(arguments) - set(parameters["properties"]) or not set(parameters["required"]).issubset(arguments):
            raise ValueError("Неверные аргументы инструмента")
        if any(not isinstance(v, str) or len(v) > (100000 if k == "content" else 1000) for k, v in arguments.items()):
            raise ValueError("Аргументы инструмента превышают ограничения")
        if name=='ask_user':
            choices=list(dict.fromkeys(v.strip() for v in arguments['choices'].splitlines() if v.strip()))
            question=arguments['question'].strip()
            if not question or len(question)>240 or not 2<=len(choices)<=5 or any(len(v)>160 for v in choices):raise ValueError('Нужен вопрос и от 2 до 5 коротких вариантов')
            return {'question':question,'options':choices}
        workspace = settings["workspace"]
        if name=='project_mkdir' and workspace:
            root=Path(workspace).resolve(strict=True);requested=Path(arguments['path'])
            if (requested.is_absolute() and requested==root) or (str(requested)=='.' and not settings.get('task_folder')):
                self.store.audit(name,'already_exists')
                return {'path':'.','absolute_path':str(root),'created':False,'status':'ready'}
        if 'path' in arguments and name in ('project_read','project_check','propose_write','project_mkdir'):
            requested=Path(arguments['path'])
            if settings.get('task_folder') and not requested.is_absolute():
                prefix=Path(settings['task_folder']).resolve().relative_to(Path(workspace).resolve(strict=True))
                if requested.parts[:len(prefix.parts)]!=prefix.parts:requested=prefix/requested
            target=safe_path(workspace,str(requested))
            arguments={**arguments,'path':str(target.relative_to(Path(workspace).resolve(strict=True)))}
        if name.startswith('desktop_'):
            desktop=getattr(self,'desktop',None)
            if desktop is None:raise ValueError('Компьютерные действия не подключены')
            from .desktop_controls import windows,window_action
            if name=='desktop_mkdir':result=desktop.create_folder(arguments['name'],{},on_desktop=not Path(arguments['name'].strip('"«»')).is_absolute())
            elif name=='desktop_launch':result=desktop.launch(arguments['name'])
            elif name=='desktop_windows':result=windows()
            elif name=='desktop_window':result=window_action(arguments['action'],arguments['query'])
            else:raise ValueError('Неизвестное действие')
        elif name == "project_build":
            from .project_build import build
            result=build(workspace,arguments["kind"])
        elif name == "calculator":
            result = {"value": calculator(arguments["expression"])}
        elif name == "knowledge_search":
            result = self.knowledge.search(arguments["query"], settings["semantic_rag"])
        elif name == "project_list":
            result = {"files": list(self.files(workspace)), "limit": 600}
        elif name == "project_read":
            path = safe_path(workspace, arguments["path"], True)
            if path.stat().st_size > 200000:
                raise ValueError("Файл больше 200 КБ")
            result = {"path": arguments["path"], "content": path.read_text(encoding="utf-8")[:20000], "limit_chars": 20000}
        elif name=='project_mkdir':
            directory=safe_path(workspace,str(Path(arguments['path'])/'.codi-directory-marker.txt')).parent
            existed=directory.is_dir()
            directory.mkdir(parents=True,exist_ok=True)
            result={'path':arguments['path'],'absolute_path':str(directory),'created':not existed,'status':'ready'}
        elif name == "project_search":
            query = arguments["query"].lower()
            if not query:
                raise ValueError("Пустой запрос")
            matches = []
            for relative in self.files(workspace):
                try:
                    for line, text in enumerate(safe_path(workspace, relative, True).read_text(encoding="utf-8").splitlines(), 1):
                        if query in text.lower():
                            matches.append({"path": relative, "line": line, "text": text[:500]})
                            if len(matches) >= 40:
                                break
                except (OSError, UnicodeError, ValueError):
                    continue
                if len(matches) >= 40:
                    break
            result = {"matches": matches, "limit": 40}
        elif name == 'project_check':
            path = safe_path(workspace,arguments['path'],True)
            if path.stat().st_size > 200000:
                raise ValueError('Файл больше 200 КБ')
            source = path.read_text(encoding='utf-8-sig');details={}
            if path.suffix=='.py':
                ast.parse(source,filename=arguments['path'])
            elif path.suffix.lower() in ('.json','.gltf'):
                json.loads(source)
            elif path.suffix.lower()=='.svg':details=check_svg(source)
            elif path.suffix.lower()=='.obj':details=check_obj(source)
            else:
                raise ValueError('Доступны проверки Python, JSON/glTF, SVG и OBJ; для других языков нужен соответствующий компилятор')
            result = {'path':arguments['path'],'syntax':'valid','executed':False,'tests_run':False,**details}
        elif name == "propose_write":
            path = safe_path(workspace, arguments["path"])
            if path.exists() and path.stat().st_size > 200000:
                raise ValueError("Файл больше 200 КБ")
            old = path.read_bytes() if path.exists() else b""
            old_text = old.decode("utf-8")
            content = arguments["content"]
            if '\x00' in content or '\x00' in old_text:
                raise ValueError('Двоичные данные не поддерживаются этим инструментом')
            diff = "".join(difflib.unified_diff(old_text.splitlines(keepends=True), content.splitlines(keepends=True), fromfile=arguments["path"], tofile=arguments["path"]))
            ident = new_id()
            # Presence participates in the hash: empty file != missing file.
            old_hash = ("present:" if path.exists() else "absent:") + digest(old)
            with self.store.db() as db:
                db.execute("INSERT INTO proposals VALUES(?,?,?,?,?,?,?,?)", (ident, str(Path(workspace).resolve()), arguments["path"], old_hash, content, diff, "pending", time.time()))
            result = {"proposal_id": ident, "path": arguments["path"], "diff": diff, "status": "awaiting_user_review", "file_written": False}
        else:
            raise ValueError("Неизвестный инструмент")
        self.store.audit(name, "ok")
        return result

    def apply(self, ident, active_workspace):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM proposals WHERE id=?", (ident,)).fetchone()
            if not row or row["status"] != "pending":
                raise ValueError("Предложение не найдено или уже обработано")
            if not active_workspace or str(Path(active_workspace).resolve()) != row["workspace"]:
                raise ValueError("Папка проекта изменилась. Создайте новое предложение")
            path = safe_path(row["workspace"], row["path"])
            if path.suffix.lower()=='.py':
                ast.parse(row['content'],filename=row['path'])
            if path.suffix.lower() in ('.json','.gltf'):
                json.loads(row['content'])
            if path.suffix.lower()=='.svg':check_svg(row['content'])
            if path.suffix.lower()=='.obj':check_obj(row['content'])
            old = path.read_bytes() if path.exists() else b""
            current_hash = ("present:" if path.exists() else "absent:") + digest(old)
            if current_hash != row["old_hash"]:
                raise ValueError("Файл изменился после создания diff. Создайте новое предложение")
            backup = self.backups / ident
            backup.mkdir(parents=True, exist_ok=True)
            if path.exists():
                shutil.copy2(path, backup / "original")
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".codi-" + ident + ".tmp")
            try:
                temporary.write_text(row["content"], encoding="utf-8", newline="")
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
            actual=path.read_bytes();expected=digest(row['content'].encode('utf-8'))
            if digest(actual)!=expected:raise ValueError('Запись не подтверждена проверкой файла на диске: '+str(path))
            db.execute("UPDATE proposals SET status='applied' WHERE id=?", (ident,))
        self.store.audit("apply_write", row["path"])
        return {"status":"applied","backup":str(backup),"read_back_verified":True,"file_written":True,"absolute_path":str(path),"path":row["path"],"sha256":expected,"bytes_written":len(actual)}

    def undo(self, ident, active_workspace):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM proposals WHERE id=?", (ident,)).fetchone()
            if not row or row["status"] != "applied":
                raise ValueError("Нет применённого изменения для отката")
            if not active_workspace or str(Path(active_workspace).resolve()) != row["workspace"]:
                raise ValueError("Папка проекта изменилась")
            path = safe_path(row["workspace"], row["path"], True)
            if digest(path.read_bytes()) != digest(row["content"].encode("utf-8")):
                raise ValueError("Файл изменился после применения; автоматический откат запрещён")
            if row["old_hash"].startswith("present:"):
                backup = self.backups / ident / "original"
                if not backup.is_file():
                    raise ValueError("Резервная копия отсутствует")
                shutil.copy2(backup, path)
            else:
                path.unlink()
            db.execute("UPDATE proposals SET status='undone' WHERE id=?", (ident,))
        self.store.audit("undo_write", row["path"])
        return {"status": "undone"}
