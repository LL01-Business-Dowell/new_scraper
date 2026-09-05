FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /usr/src/app

# Install system dependencies & ffmpeg in a single layer
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /usr/src/app/
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir gunicorn

# Copy application code
COPY . /usr/src/app/

RUN chmod +x /usr/src/app/manage.py

EXPOSE 8004

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8004", "--workers", "1", "--preload", "--timeout", "300"]