"""Validated settings, modes and honest model identities."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
WEB = ROOT / "web"
OLLAMA = "http://127.0.0.1:11434"
TIERS = [
    {"id": "light", "name": "Initial 0.1", "backend": "qwen3:1.7b", "size_gb": 1.4, "ram_gb": 8, "description": "Лёгкая модель для простых задач"},
    {"id": "balanced", "name": "Initial 0.2", "backend": "qwen3:4b-instruct", "size_gb": 2.5, "ram_gb": 12, "description": "Основная модель: прямые ответы и работа с кодом"},
    {"id": "powerful", "name": "Initial 0.3", "backend": "qwen3:8b", "size_gb": 5.2, "ram_gb": 16, "description": "Больше качество, выше расход памяти"},
    {"id": "maximum", "name": "InitialMega", "backend": "qwen3:30b-instruct", "size_gb": 19, "ram_gb": 32, "description": "Для рабочих станций. Не загружается автоматически"},
]
MODES = {
    "artist":{"name":"3D и персонажи","icon":"palette","instruction":"Создавай 3D-ассеты, модели для игр и иллюстрации персонажей. При ясном запросе выполняй задачу в выбранной папке. Для 3D можно создавать OBJ/MTL, glTF JSON или Python-скрипт для Blender. Для рисунков и аватаров создавай полноценный SVG с читаемым силуэтом, согласованной палитрой и отдельными группами. Учитывай референс пользователя: пропорции, волосы, глаза, одежду и узнаваемые детали. Для 3D соблюдай масштаб, нормали, замкнутость сетки где нужна, разумное число полигонов и материалы. Для Blender используй актуальный bpy API, не удаляй чужие объекты сцены. Не называй Python-скрипт готовым blend-файлом: файл .blend возникает только после запуска в Blender. Не заявляй о рендере, проверке внешнего вида или экспорте без результата инструмента. Растровый генератор изображений не подключён; не выдавай SVG за работу диффузионной модели."},
    'super':{'name':'Поиск','icon':'search','instruction':'Исследуй вопрос по реально прочитанным интернет-источникам. Сопоставляй сведения, указывай источники и ограничения. Не называй предположения установленными фактами.'},
    'desktop':{'name':'Компьютер','icon':'computer','instruction':'Ты локальный помощник по работе с компьютером. Умеешь анализировать присланные снимки экрана, читать и изменять выбранные текстовые файлы, создавать файлы в выбранной папке. Команды «открой Блокнот», «удали этот файл», «запомни это» выполняются отдельным контроллером; не выдумывай их выполнение. Для удаления попроси выбрать файл и отправить точную команду «удали этот файл». Терминал и произвольные клики пока не подключены. Уточняй неоднозначный объект. Используй память для привычек и примеров прошлой работы.'},
    "vibecoding": {"name": "Code With Codi", "icon": "code", "instruction": "Ты напарник по разработке. Превращай идею в небольшие рабочие изменения. Если подключена папка, сначала изучи файлы через project_list/project_read, затем предложи короткий план и правки через propose_write. Не меняй несвязанные части. Для ошибки найди причину в коде. Проверяй синтаксис Python/JSON через project_check. После правок объясни запуск и конкретную проверку. Используй project_build для тестов Python, npm и сборки Android. Проверяй exit_code и artifacts; APK создаётся сборщиком, а не записью текстового файла. Если задача неоднозначна, уточни предпочтения коротким вопросом с вариантами. Когда папки нет, дай готовый код и предложи подключить проект."},
    "general": {"name": "Ассистент", "icon": "✦", "instruction": "Помогай с повседневными и сложными задачами. Отвечай ясно и по существу."},
    "programmer": {"name": "Программист", "icon": "⌘", "instruction": "Изучай проект доступными инструментами. Для изменения файлов обязательно вызывай propose_write с полным новым текстом файла: текстовый diff не создаёт предложение. Проверяй гипотезы, объясняй код. Не заявляй о выполненных тестах без их результатов."},
    "teacher": {"name": "Учитель", "icon": "◎", "instruction": "Объясняй на простых примерах с учётом уровня ученика. Давай упражнения и обратную связь. При самостоятельном решении сначала предложи подсказку; полный ответ давай по запросу."},
    "roleplay": {"name": "Ролёвка", "icon": "☾", "instruction": "Следуй выбранным миру, жанру и ролям. Не управляй действиями и чувствами персонажа пользователя. Сохраняй сюжет. Отделяй вымысел от реальности; /ooc означает разговор вне роли."},
    "researcher": {"name": "Исследователь", "icon": "⌕", "instruction": "Используй загруженную базу знаний. Указывай источники [название, фрагмент]. Для изучения сайтов пользователь может написать «изучи тему» и открыть Память: там сохраняются конспекты, источники и сравнение. В ответе используй только реально найденные материалы, не выдумывай ссылки и свежие факты."},
    "writer": {"name": "Писатель", "icon": "✎", "instruction": "Помогай с идеями, сюжетом, структурой и редактурой. Сохраняй голос автора."},
    "translator": {"name": "Переводчик", "icon": "文", "instruction": "Переводи с сохранением смысла, регистра и терминологии. Уточняй существенные неоднозначности."},
    "analyst": {"name": "Аналитик", "icon": "▥", "instruction": "Проверяй числа, единицы и допущения. Для арифметики используй calculator. Показывай воспроизводимый метод."},
    "planner": {"name": "Планировщик", "icon": "◷", "instruction": "Разбивай цель на реалистичные этапы и зависимости. Планировщик уведомлений пока не подключён, поэтому не обещай автоматические напоминания."},
    "designer": {"name": "Дизайнер", "icon": "◇", "instruction": "Помогай с визуальным брифом, стилем, интерфейсами и персонажами. Можно создавать SVG-иллюстрации и HTML/CSS в выбранной папке через инструменты файлов. Сохраняй узнаваемые детали референса и гармоничную палитру. Растровая AI-генерация изображений пока не подключена; не утверждай, что нарисовал PNG, если создан SVG."},
}
DEFAULTS = {
    "model": "qwen3:1.7b", "mode": "general", "name": "CodiAI", "language": "ru",
    "tone": "Дружелюбный", "verbosity": "Средняя", "temperature": 0.4,
    "num_ctx": 4096, "num_predict": 768, "thinking": False,
    "memory_enabled": False, "tools_enabled": False, "rag_enabled": True,
    "workspace": "", "skin": "original", "custom_instruction": "",
    "roleplay_world": "", "roleplay_character": "", "teacher_level": "Начинающий",
    "embedding_model": "embeddinggemma", "semantic_rag": True,
    "theme": "codi", "animations": False,
    "project_autowrite": True,
    "super_sources": 8,
}

def validate_settings(current: dict, patch: dict, modes: dict) -> dict:
    if not isinstance(patch, dict) or set(patch) - set(DEFAULTS):
        raise ValueError("Неизвестные параметры конфигурации")
    result = {**current, **patch}
    if type(result['super_sources']) is not int or result['super_sources'] not in (4,8,12):raise ValueError('Поиск: выберите 4, 8 или 12 источников')
    for key in ("memory_enabled", "tools_enabled", "rag_enabled", "thinking", "semantic_rag", "animations",'project_autowrite'):
        if type(result[key]) is not bool:
            raise ValueError(f"{key}: требуется логическое значение")
    for key, low, high in (("temperature", 0, 2), ("num_ctx", 2048, 16384), ("num_predict", 128, 8192)):
        value = result[key]
        if type(value) not in (int, float) or not low <= value <= high:
            raise ValueError(f"{key}: допустимо от {low} до {high}")
        if key != "temperature" and type(value) is not int:
            raise ValueError(f"{key}: требуется целое число")
    for key, value in result.items():
        if key in DEFAULTS and isinstance(DEFAULTS[key], str):
            if not isinstance(value, str) or len(value) > (5000 if key.endswith("instruction") else 1500):
                raise ValueError(f"Недопустимое значение {key}")
    if result["model"] not in [t["backend"] for t in TIERS]:
        raise ValueError("Выберите локальную модель из каталога")
    if result['model'].endswith('-instruct') and result['thinking']:
        raise ValueError('Эта модель даёт прямые ответы. Для длительного обдумывания выберите Initial 0.1')
    if result["embedding_model"] != "embeddinggemma":
        raise ValueError("Неподдерживаемая embedding-модель")
    if result["theme"] not in ("codi", "ice", "violet", "rose", "amber", "graphite"):
        raise ValueError("Неизвестная тема оформления")
    if result["mode"] not in modes or result["skin"] not in ("original", "programmer", "teacher"):
        raise ValueError("Неизвестный режим или образ")
    if result["workspace"]:
        path = Path(result["workspace"]).expanduser().resolve(strict=True)
        if not path.is_dir() or path == Path(path.anchor):
            raise ValueError("Выберите отдельную папку проекта, не весь диск")
        result["workspace"] = str(path)
    return result
