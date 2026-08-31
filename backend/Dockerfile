# Backend Dockerfile
# OCR via OCR.space API (lightweight — no heavy local OCR dependencies).
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed by some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer caching — only re-runs when
# requirements.txt changes, not on every code edit)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create directories that will be backed by Docker volumes so they
# survive container restarts even when the image is rebuilt.
RUN mkdir -p /app/db_data /app/uploaded_documents

# Copy the rest of the application code
COPY . .

EXPOSE 8000

# Seed + run. Seed is idempotent (skips if DB already populated).
CMD ["sh", "-c", "python seed.py && uvicorn main:app --host 0.0.0.0 --port 8000"]
