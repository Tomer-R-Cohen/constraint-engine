# The engine as an MCP server over streamable HTTP, for hosting (e.g. Railway).
# Listens on [::]:8000 (IPv4 and IPv6, for private networks); path /mcp.
FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["constraint-engine-mcp", "--transport", "streamable-http", "--host", "::", "--port", "8000"]
