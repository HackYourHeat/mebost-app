FROM python:3.11-slim

# Tránh interactive prompts khi cài apt
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Cài system deps (cần cho psycopg2-binary nếu dùng sau)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Cài Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Tạo thư mục cần thiết
RUN mkdir -p logs/users logs/analytics data static

# Railway inject PORT tự động
EXPOSE 8080

# Pre-deploy migration + start
CMD python migrate.py && gunicorn app:app \
    --bind 0.0.0.0:${PORT:-8080} \
    --workers 2 \
    --timeout 120 \
    --keep-alive 5 \
    --log-level info \
    --access-logfile -
