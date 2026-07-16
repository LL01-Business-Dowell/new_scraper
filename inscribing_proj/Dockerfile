# # Use a Python base image
# FROM python:3.11

# # Set environment variables
# ENV PYTHONDONTWRITEBYTECODE 1
# ENV PYTHONUNBUFFERED 1

# # Set the working directory
# WORKDIR /usr/src/app

# # Install dependencies
# COPY requirements.txt /usr/src/app/
# RUN pip install --no-cache-dir -r requirements.txt

# # Copy the rest of the application code
# COPY . /usr/src/app/

# # Re-add execution permission to manage.py inside the container
# RUN chmod +x /usr/src/app/manage.py

# # Port the application runs on
# EXPOSE 8002

# # Command to run the Django development server
# # IMPORTANT: It must run on 0.0.0.0 and on the EXPOSEd port
# CMD ["python", "manage.py", "runserver", "0.0.0.0:8002"]

# inscribing_proj/Dockerfile
# --------------------------
# Django inscriber microservice.
# Uses gunicorn instead of manage.py runserver — runserver is single-threaded
# and not suitable for production. Gunicorn handles concurrent requests properly
# which matters because the backend makes parallel tile-fetch calls.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /usr/src/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /usr/src/app/
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir gunicorn

# Copy application code
COPY . /usr/src/app/

RUN chmod +x /usr/src/app/manage.py

EXPOSE 8002

# gunicorn with 3 workers — handles concurrent requests from the backend
# Use shell form so $PORT env var works on cloud platforms
CMD ["gunicorn", "inscribing_proj.wsgi:application", "--bind", "0.0.0.0:8002", "--workers", "3", "--timeout", "300"]
