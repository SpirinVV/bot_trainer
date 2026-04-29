# Используем официальный образ Python 3.12 slim
FROM python:3.12-slim

# Устанавливаем локали
RUN apt-get update && apt-get install -y locales && \
    sed -i '/ru_RU.UTF-8/s/^# //g' /etc/locale.gen && \
    locale-gen && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV LANG=ru_RU.UTF-8
ENV LANGUAGE=ru_RU:ru
ENV LC_ALL=ru_RU.UTF-8

# Создаем пользователя и группу botuser
RUN groupadd -r botuser && useradd -r -g botuser -u 1000 botuser

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта (.env исключён через .dockerignore — подаётся через env_file в compose.yml)
COPY . .

# Создаем директорию для базы данных
RUN mkdir -p /app/data /app/backups

# Устанавливаем переменные окружения для Python
ENV PYTHONUNBUFFERED=1
ENV TZ="Europe/Moscow"
