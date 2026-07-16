FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libzbar0 \
    && rm -rf /var/lib/apt/lists/*

# Copy project
COPY pyproject.toml /app/
COPY sellfox_shipping/ /app/sellfox_shipping/

# Install deps
RUN pip install --no-cache-dir \
    fastapi>=0.136.3 \
    uvicorn>=0.49.0 \
    pyyaml>=6.0 \
    httpx>=0.27 \
    jinja2>=3.0 \
    pydantic>=2.0 \
    fastmcp \
    typer

# Data volume
RUN mkdir -p /app/sellfox_shipping/data /app/sellfox_shipping/out

EXPOSE 8401

CMD ["uvicorn", "sellfox_shipping.main:app", "--host", "0.0.0.0", "--port", "8401"]
