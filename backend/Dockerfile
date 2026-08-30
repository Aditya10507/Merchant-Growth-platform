# Backend Dockerfile
# PaddleOCR is large; first build downloads model weights on first OCR call.
# Uses python:3.11-slim to keep the image lean while supporting all deps.
FROM python:3.11-slim

WORKDIR /app

# System deps required by OpenCV / PaddleOCR at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
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

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
