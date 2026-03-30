FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies first (better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user and directories
RUN useradd --create-home --shell /bin/bash appuser && \
    mkdir -p /app/data /app/logs && \
    chown -R appuser:appuser /app

USER appuser

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV TZ=America/New_York

# Default command - run the scanner
CMD ["python", "run_scanner.py"]
