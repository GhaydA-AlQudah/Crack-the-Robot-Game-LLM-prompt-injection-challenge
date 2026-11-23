FROM python:3.12-slim

WORKDIR /app

COPY requirements-Runtime.txt .

RUN pip install --no-cache-dir -r requirements-Runtime.txt

COPY . .

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]