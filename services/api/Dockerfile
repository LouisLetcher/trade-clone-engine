FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md alembic.ini ./
COPY trade_clone_engine ./trade_clone_engine
COPY services/api ./services/api
COPY alembic ./alembic
COPY entrypoint.sh ./entrypoint.sh

RUN pip install --upgrade pip && pip install -e .

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
