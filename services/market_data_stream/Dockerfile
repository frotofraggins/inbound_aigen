FROM python:3.10-slim

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy configuration and database modules
COPY config.py ./config.py
COPY db.py ./db.py

# Copy signal processing logic
COPY rules.py ./rules.py
COPY gap_fade.py ./gap_fade.py

# Copy WebSocket service with bar storage
COPY main.py .

# Run the service
CMD ["python", "main.py"]
