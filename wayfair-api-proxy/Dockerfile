FROM python:3.12-slim

RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /data && chown -R appuser:appuser /data /app

USER appuser
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8410

CMD ["uvicorn", "main:create_runtime_app", "--factory", "--host", "0.0.0.0", "--port", "8410", "--log-level", "info"]
