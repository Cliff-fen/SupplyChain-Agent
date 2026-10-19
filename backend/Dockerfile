FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 RUFF_CACHE_DIR=/tmp/supplymind-ruff
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL} PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
# Keep dependency installation independent of application source changes.  The
# package placeholder satisfies setuptools; the real package is copied below.
RUN mkdir -p app && touch app/__init__.py
RUN pip install --no-cache-dir ".[dev]"
ENV PYTHONPATH=/app
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
COPY tests ./tests
RUN useradd --uid 10001 --create-home app \
    && mkdir -p /app/backenddata /app/output /app/data/reports /data/documents /data/reports \
    && chown -R app:app /app/backenddata /app/output /app/data /data
USER 10001:10001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
