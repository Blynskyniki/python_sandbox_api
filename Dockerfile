# Используем минимальный официальный образ Python
FROM python:3.11-slim

# Установка зависимостей системы (для работы resource и subprocess)
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Установка рабочей директории
WORKDIR /app

# Копируем зависимости и код
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Устанавливаем переменные окружения
ENV CPU_LIMIT_SECONDS=2
ENV MEMORY_LIMIT_MB=64
ENV EXEC_TIMEOUT_SECONDS=3

# Запуск FastAPI приложения через Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]