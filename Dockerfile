FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install dependencies (no dev extras)
RUN uv pip install --system --no-cache .

# Expose stdio transport (MCP default)
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=WARNING

# Glama check: server must start and respond to MCP introspection
CMD ["brief-mcp"]
