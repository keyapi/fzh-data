FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

EXPOSE 8090
# Lesson 59: uvicorn log_level=info so boot logs are visible
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8090", "--log-level", "info"]
