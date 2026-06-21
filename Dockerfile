# EHR Data Quality Checker — production image
FROM python:3.12-slim AS base

# Faster, quieter Python in containers
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# Install dependencies first so the layer caches across code changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code and bundled sample data
COPY app/ ./app/
COPY sample_data/ ./sample_data/

# Run as an unprivileged user
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,os,sys; p=os.environ.get('PORT','8000'); sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+p+'/api/health').status==200 else 1)"

# Shell form so $PORT expands; default 8000, override with -e PORT=...
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
