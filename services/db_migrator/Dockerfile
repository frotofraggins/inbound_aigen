FROM python:3.12-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY services/db_migrator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy migration script
COPY services/db_migrator/migrate.py .
RUN chmod +x migrate.py

# Copy migrations directory
COPY db/migrations /migrations

# Run migrations on container start
CMD ["python", "migrate.py"]
