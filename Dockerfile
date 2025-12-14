FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    freeipa-client \
    krb5-user \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    docker \
    pyyaml

# Create working directory
WORKDIR /app

# Copy script
COPY dns-automation.py /app/
COPY web_catalog.py /app/
COPY entrypoint.sh /app/

# Create directories
RUN mkdir -p /config /logs

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Run entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

