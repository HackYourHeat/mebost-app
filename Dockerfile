FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p logs/users logs/analytics data static

EXPOSE 8080

CMD ["sh", "-c", "python migrate.py && gunicorn app:app --bind 0.0.0.0:${PORT:-8080} --workers 2 --timeout 120 --keep-alive 5 --log-level info --access-logfile -"]