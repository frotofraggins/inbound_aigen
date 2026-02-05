FROM python:3.11-slim
# CACHE BUST: 2026-02-03-16:20 - Use close_position API instead of manual sell orders

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the position manager
CMD ["python", "main.py"]
