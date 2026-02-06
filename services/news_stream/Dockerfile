FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules (already copied to local dir)
COPY config.py ./config.py
COPY db.py ./db.py

# Copy WebSocket service
COPY main.py .

# Run the service
CMD ["python", "main.py"]
