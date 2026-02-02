FROM python:3.12-slim
# CACHE BUST: 2026-01-30-16-17 - Convert to ECS Service mode

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY config.py store.py main.py ./
COPY sources/ ./sources/

# Run as non-root user for security
RUN useradd -m -u 1000 worker && chown -R worker:worker /app
USER worker

# Set Python to unbuffered mode for real-time logs
ENV PYTHONUNBUFFERED=1

# Default environment variables
ENV AWS_REGION=us-west-2
ENV LOOKBACK_MINUTES=120
ENV INTERVAL=1m

# Run the ingestor
CMD ["python", "main.py"]
