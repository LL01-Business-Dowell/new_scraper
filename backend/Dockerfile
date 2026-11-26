# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /usr/src/app

# 1. Install Chromium + chromedriver without bloated recommended packages
RUN apt-get update && apt-get install -y --no-install-recommends \
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

# 2. Install CPU-only PyTorch FIRST in its own cached layer so it never re-downloads
#    when you add small packages (like httpx) to requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# 3. Copy and install remaining Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && python -m nltk.downloader -d /usr/local/share/nltk_data vader_lexicon

# 4. Copy application code
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]