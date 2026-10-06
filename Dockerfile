# Dockerfile
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

# Папка для базы данных (для монтирования Volume в Cloud.ru)
RUN mkdir -p /data

CMD ["python", "main.py"]