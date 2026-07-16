FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /usr/src/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install ffmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /usr/src/app/
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir gunicorn

# Copy application code
COPY . /usr/src/app/

RUN chmod +x /usr/src/app/manage.py

EXPOSE 8003

# gunicorn with 3 workers — handles concurrent requests from the backend
# Use shell form so $PORT env var works on cloud platforms
# CMD gunicorn my_project.wsgi:application --bind 0.0.0.0:8002 --workers 3 --preload

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8003", "--workers", "1", "--preload", "--timeout", "300"]