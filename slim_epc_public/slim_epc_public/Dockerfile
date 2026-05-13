FROM 3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Install curl for uv install script
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install uv (Astral) package manager
RUN curl -LsSfvvv https://astral.sh/uv/install.sh | sh

COPY pyproject.toml .
RUN uv lock && uv sync --frozen --no-install-project

COPY . .

RUN mkdir -p /data
ENV EPC_DB_PATH=/data/epc.db
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
