FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# System dependencies for CadQuery (OpenCASCADE OCCT)
RUN apt-get update && apt-get install -y --no-install-recommends \
    fontconfig \
    fonts-dejavu \
    fonts-freefont-ttf \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application codebase
COPY . .

# Ensure output directory exists
RUN mkdir -p output

# Expose default port
EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/api/health || exit 1

# Support dynamic $PORT for cloud PaaS (Render, Railway, Cloud Run) and default to 8501
ENTRYPOINT ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8501}"]
