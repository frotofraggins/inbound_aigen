FROM python:3.12-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY services/rss_ingest_task/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy ingestion script
COPY services/rss_ingest_task/ingest.py .
RUN chmod +x ingest.py

# Run ingestion on container start
CMD ["python", "ingest.py"]
