# -----------------------
# Stage 1: Builder
# -----------------------
FROM python:3.12-slim AS builder

WORKDIR /app

# Кэшируем зависимости
COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . /app

# -----------------------
# Stage 2: Runtime
# -----------------------
FROM python:3.12-slim

WORKDIR /app

# Копируем виртуальное окружение и проект из builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

ENV PATH="/opt/venv/bin:$PATH"

# Делаем скрипт entrypoint исполняемым
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
