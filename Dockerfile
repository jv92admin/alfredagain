# Alfred V2 - Production Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy all package files (need src/ for pip install to work)
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY prompts/ ./prompts/

# Install Python dependencies
RUN pip install --no-cache-dir .

# Copy prompts to where the installed package can find them
# The code looks 5 levels up from site-packages/alfred/graph/nodes/
RUN mkdir -p /usr/local/lib/python3.11/prompts && \
    cp -r prompts/* /usr/local/lib/python3.11/prompts/

# Expose port (Railway will set PORT env var)
EXPOSE 8000

# Health check using Railway's PORT
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Run the application
CMD ["sh", "-c", "uvicorn alfred.web.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
