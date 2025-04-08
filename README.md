📦 Python Sandbox API

Асинхронный HTTP API-сервис на FastAPI для безопасного запуска пользовательского Python-кода с аргументами. Выполнение
ограничено по времени и памяти, все параметры настраиваются через .env.

### Установленные зависимости: **numpy** **pandas**

⸻

🚀 Возможности \
• 🔐 Изолированное выполнение пользовательского кода \
• ⏱ Ограничения по времени CPU и объёму памяти
**(5s CPU && 512mb RAM)** \
• 🧠 Поддержка передачи аргументов (включая сложные структуры) \
• ⚙️ Настройка через .env \
• 🧾 Ответ с stdout, stderr, exit_code

⸻

🔧 Установка

git clone python-sandbox-api
cd python-sandbox-api
python -m venv venv
source venv/bin/activate # или venv\Scripts\activate на Windows
pip install -r requirements.txt

Создай .env:

CPU_LIMIT_SECONDS=2
MEMORY_LIMIT_MB=64
EXEC_TIMEOUT_SECONDS=3

⸻

🏁 Запуск

```
uvicorn main:app --reload

```

⸻

📡 API

POST /run

Запуск пользовательского кода.

🔸 Тело запроса (JSON)

```
{
  "code": "def run(user): return f\"{user['first_name']} {user['last_name']}\"",
  "args": [
    {
      "first_name": "Иван",
      "last_name": "Петров"
    }
  ]
}
```

**Важно: должен быть определён def run(...), именно эта функция вызывается с аргументами.**

🔸 Ответ (JSON)

{
"stdout": "Иван Петров",
"stderr": "",
"exit_code": 0
}

🔸 Ошибки
• 400: ошибка выполнения, синтаксис, превышение лимитов
• 408: превышено время выполнения
• 422: ошибка валидации запроса
• 500: внутренняя ошибка

⸻

🧪 Пример с curl

curl -X POST http://localhost:8000/run \
-H "Authorization: Basic c2FuZGJveDpzZWNyZXQxMjM=" \
-H "Content-Type: application/json" \
-d '{
"code": "def run(user): return f\"{user[\'first_name\']} {user[\'last_name\']}\"",
"args": [{"first_name": "Иван", "last_name": "Петров"}]
}'

⸻

🛡 Безопасность
• На Linux используются resource.setrlimit для ограничения CPU и памяти.
• На других ОС лимиты не применяются.
• Для более надёжной изоляции рекомендуется запуск кода в Docker или с использованием gVisor/Firejail.

⸻

📂 Файлы

Файл Назначение
main.py Основной API-сервер
.env Параметры ограничений
requirements.txt Зависимости (fastapi, python-dotenv)

