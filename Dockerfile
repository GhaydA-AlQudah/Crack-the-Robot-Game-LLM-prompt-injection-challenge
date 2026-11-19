
FROM python:3.12-slim

WORKDIR /app

COPY requirements-Runtime.txt .

RUN pip install --no-cache-dir -r requirements-Runtime.txt

COPY . .

CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
