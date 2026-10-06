FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Сертификат Минцифры для GigaChat
RUN curl -k "https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt" \
        -o /tmp/russian_trusted_root_ca.crt \
    && cat /tmp/russian_trusted_root_ca.crt >> $(python -m certifi) \
    && rm /tmp/russian_trusted_root_ca.crt

COPY . .

# Создаём пользователя с UID 1000 и даём права на директории
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home appuser \
    && mkdir -p /app/logs /data \
    && chown -R 1000:1000 /app /data

# Переключаемся на этого пользователя
USER 1000

CMD ["python", "main.py"]