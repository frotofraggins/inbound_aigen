FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY discovery.py .

# Run as non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Run the service
CMD ["python", "-u", "discovery.py"]
