# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /usr/src/app

# Install Chromium + chromedriver for Selenium scraping
# plus curl/ca-certificates for outbound HTTP (Gemini API, Datacube) and ffmpeg for audio analysis
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    curl \
    ca-certificates \
    ffmpeg \
    libjpeg-dev \
    zlib1g-dev \
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