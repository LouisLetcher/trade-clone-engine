FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md alembic.ini ./
COPY trade_clone_engine ./trade_clone_engine
COPY services/solana_executor ./services/solana_executor
COPY config ./config
COPY alembic ./alembic
COPY entrypoint.sh ./entrypoint.sh

RUN pip install --upgrade pip && pip install -e .

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "services/solana_executor/main.py"]

