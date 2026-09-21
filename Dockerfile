FROM python:3.11-slim

# System deps — bash + curl + nodejs + git + jq (container per plan.md:247-249)
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    curl \
    ca-certificates \
    nodejs \
    npm \
    git \
    jq \
    && rm -rf /var/lib/apt/lists/* \
    && node --version && npm --version

WORKDIR /app

# Python deps (layer cache)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Install opencode (official install, not npm) — single container LLM adapter per plan.md:100-104
RUN curl -fsSL https://opencode.ai/install | bash \
    && ln -sf /root/.opencode/bin/opencode /usr/local/bin/opencode \
    && opencode --version \
    && chmod +x docker-entrypoint.sh

# Ensure dirs + perms for plug-and-play (volumes optional)
RUN mkdir -p /app/instances/temp /app/instances/chats /app/instances/logs \
    && chmod +x tasks/*/run.sh 2>/dev/null || true

ENV PYTHONPATH=/app \
    NODE_ENV=production \
    PORT=31415 \
    HOST=0.0.0.0

EXPOSE 31415

# Healthcheck for plug-and-play — fun port 31415 = π 3.1415... (not 8080, not lame, memorable, irrational like Banana)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fs http://localhost:31415/api/health || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gui"]
