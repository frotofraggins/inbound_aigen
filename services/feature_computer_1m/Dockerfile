FROM python:3.12-slim

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
COPY config.py db.py features.py main.py ./

# Run as non-root user
RUN useradd -m -u 1000 worker && chown -R worker:worker /app
USER worker

# Python unbuffered for real-time logs
ENV PYTHONUNBUFFERED=1

# Run the feature computer
CMD ["python", "main.py"]
