# Stage 1: fetch supercronic binary
FROM debian:bookworm-slim AS supercronic

ARG SUPERCRONIC_VERSION=v0.2.29
ARG SUPERCRONIC_SHA1SUM=cd48d45c4b10f3f0bfdd3a57d054cd05ac96812b
ARG TARGETARCH

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && ARCH=$(case "${TARGETARCH}" in \
        "amd64") echo "linux-amd64" ;; \
        "arm64") echo "linux-arm64" ;; \
        *) echo "linux-amd64" ;; \
    esac) \
    && curl -fsSLO "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-${ARCH}" \
    && mv "supercronic-${ARCH}" /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic

# Stage 2: application
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy supercronic from stage 1
COPY --from=supercronic /usr/local/bin/supercronic /usr/local/bin/supercronic

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and Chromium
RUN pip install --no-cache-dir playwright \
    && playwright install chromium \
    && playwright install-deps chromium

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p /app/data/logs /app/data/cache /app/data/archive /app/data/screenshots

# Copy crontab
COPY crontab /app/crontab

CMD ["supercronic", "/app/crontab"]
