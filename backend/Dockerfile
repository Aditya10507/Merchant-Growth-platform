# Backend Dockerfile
# Uses Google Cloud Vision for OCR (no heavy PaddleOCR dependencies).
# Image is much smaller and builds faster than before.
FROM python:3.11-slim

WORKDIR /app

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

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
