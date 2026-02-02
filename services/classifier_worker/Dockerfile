FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download FinBERT model at build time to cache it in the image
# This reduces cold start time significantly
RUN python -c "from transformers import AutoTokenizer, AutoModelForSequenceClassification; \
    AutoTokenizer.from_pretrained('ProsusAI/finbert'); \
    AutoModelForSequenceClassification.from_pretrained('ProsusAI/finbert')"

# Copy application code
COPY config.py db.py main.py ./
COPY nlp/ ./nlp/

# Run as non-root user for security
RUN useradd -m -u 1000 worker && chown -R worker:worker /app
USER worker

# Set Python to unbuffered mode for real-time logs
ENV PYTHONUNBUFFERED=1

# Run the worker
CMD ["python", "main.py"]
