# # FROM python:3.11-slim

# # WORKDIR /usr/src/app

# # # Install Chromium + dependencies (ARM compatible)
# # RUN apt-get update && apt-get install -y \
# #     chromium \
# #     chromium-driver \
# #     wget \
# #     curl \
# #     unzip \
# #     gnupg \
# #     libx11-6 \
# #     libxcb1 \
# #     libxcomposite1 \
# #     libxdamage1 \
# #     libxext6 \
# #     libxfixes3 \
# #     libxkbcommon0 \
# #     libxrandr2 \
# #     xdg-utils \
# #     libglib2.0-0 \
# #     libnss3 \
# #     libx11-xcb1 \
# #     libxcursor1 \
# #     libxi6 \
# #     libxrender1 \
# #     libdbus-glib-1-2 \
# #     libgtk-3-0 \
# #     fonts-liberation \
# #     ca-certificates \
# #     && rm -rf /var/lib/apt/lists/*

# # # Tell Selenium where Chromium is
# # ENV GOOGLE_CHROME_BIN=/usr/bin/chromium
# # ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# # # Copy requirements
# # COPY requirements.txt .

# # # Install Python deps
# # RUN pip install --no-cache-dir --upgrade pip \
# #  && pip install --no-cache-dir -r requirements.txt

# # # Copy app
# # COPY . .

# # EXPOSE 8000

# # CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# FROM python:3.11-slim

# WORKDIR /usr/src/app

# # Install only the system dependencies actually needed:
# #   curl/ca-certificates — for outbound HTTP calls (Gemini API, Datacube)
# #   libgomp1            — required by some ML/numeric Python packages
# RUN apt-get update && apt-get install -y \
#     curl \
#     ca-certificates \
#     libgomp1 \
#     && rm -rf /var/lib/apt/lists/*

# # Copy and install Python dependencies first (layer cache friendly)
# COPY requirements.txt .
# RUN pip install --no-cache-dir --upgrade pip \
#  && pip install --no-cache-dir -r requirements.txt

# # Copy application code
# COPY . .

# EXPOSE 8000

# # Use shell form so $PORT env var works on platforms like Fly.io / Koyeb
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /usr/src/app

# Install Chromium + chromedriver for Selenium scraping
# plus curl/ca-certificates for outbound HTTP (Gemini API, Datacube)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    curl \
    ca-certificates \
    ffmpeg \
    libgomp1 \
    libglib2.0-0 \
    libnss3 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    libxi6 \
    libxrender1 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

ENV GOOGLE_CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && python -m nltk.downloader vader_lexicon

# Copy application code
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
