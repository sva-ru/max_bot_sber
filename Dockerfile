# Dockerfile
# Образ для бота канала «Бизнес-Фактор Юго-Запад» в MAX
# Режим работы: Long Polling (без входящих HTTP-запросов)

FROM python:3.12-slim

# Метаданные образа
LABEL maintainer="Sber SW Business Channel" \
      description="Telegram/MAX bot for Sber South-West business clients"

# Отключаем создание .pyc-файлов и включаем небуферизованный вывод
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Рабочая директория внутри контейнера
WORKDIR /app

# Системные зависимости:
# - curl нужен для скачивания сертификата Минцифры
# - ca-certificates — доверенные корневые сертификаты
# - gcc — для сборки некоторых Python-пакетов (если понадобится)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gcc \
    && rm -rf /var/lib/apt/lists/*

# Сначала копируем только requirements — это кэширует слой pip install
COPY requirements.txt .

# Устанавливаем Python-зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Добавляем корневой сертификат Минцифры в certifi
# (нужен для работы GigaChat API)
RUN curl -k "https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt" \
        -o /tmp/russian_trusted_root_ca.crt \
    && cat /tmp/russian_trusted_root_ca.crt >> $(python -m certifi) \
    && rm /tmp/russian_trusted_root_ca.crt

# Копируем весь остальной код проекта
COPY . .

# Создаём директорию для базы данных (для Volume на Railway)
RUN mkdir -p /data

# Точка входа — запуск бота
CMD ["python", "main.py"]
