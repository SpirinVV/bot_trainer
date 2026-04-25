# Используем официальный образ Python 3.12 slim
FROM python:3.12-slim

# Создаем пользователя и группу botuser
RUN groupadd -r botuser && useradd -r -g botuser -u 1000 botuser

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта
COPY . .

# Создаем директорию для базы данных
RUN mkdir -p /app/data /app/backups

# Устанавливаем переменные окружения для Python
ENV PYTHONUNBUFFERED=1
ENV TZ="Europe/Moscow"
