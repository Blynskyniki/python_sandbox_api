FROM python:3.11

RUN apt update && apt install -y build-essential gcc libatlas-base-dev libopenblas-dev liblapack-dev nano \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --upgrade pip setuptools wheel numpy pandas scipy
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