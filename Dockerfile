FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends neovim && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY misskey_cli/ misskey_cli/
ENTRYPOINT ["python", "-m", "misskey_cli"]
