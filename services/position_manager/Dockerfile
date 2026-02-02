FROM python:3.11-slim
# Cache bust: 2026-01-30-convert-to-service
# CACHE BUST: 2026-01-29-23-36 - Fix Alpaca API method

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the position manager
CMD ["python", "main.py"]
