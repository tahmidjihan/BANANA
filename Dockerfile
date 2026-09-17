FROM python:3.11-slim

# Node.js + bash + essentials (container-compatible per plan.md:247-249)
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    curl \
    nodejs \
    npm \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && node --version && npm --version

WORKDIR /app

# Python deps first for layer cache
COPY requirements.txt* ./
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi

# Copy rest (src, config, tasks, etc.)
COPY . .

# Install opencode (LLM adapter per plan.md:100-104, WORKFLOW.md:60)
# Try official npm package; fallback if not yet published
RUN npm install -g opencode-ai 2>&1 || echo "opencode-ai not found via npm, will try install script" \
    && opencode --version 2>&1 || echo "opencode not available yet - placeholder for Phase 3"

# Default sanity
CMD ["bash"]
