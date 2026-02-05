FROM python:3.12-slim

# CACHE BUST: position-intent-fix-2026-02-03-16:00
# Install system dependencies for psycopg2
RUN apt-get update && \
    apt-get install -y gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the dispatcher
CMD ["python", "main.py"]
