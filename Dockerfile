FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        neovim tzdata locales \
 && sed -i 's/^# *\(en_US.UTF-8\)/\1/; s/^# *\(ja_JP.UTF-8\)/\1/; s/^# *\(fr_FR.UTF-8\)/\1/' /etc/locale.gen \
 && locale-gen \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY misskey_cli/ misskey_cli/
COPY tests/ tests/
RUN mkdir -p /home/user/.config/misskey-cli && chmod 777 /home/user
ENV HOME=/home/user
ENTRYPOINT ["python", "-m", "misskey_cli"]
