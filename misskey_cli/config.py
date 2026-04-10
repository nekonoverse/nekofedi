import json
import os
from pathlib import Path


CONFIG_DIR = Path(os.environ.get("MISSKEY_CLI_CONFIG_DIR", Path.home() / ".config" / "misskey-cli"))
CONFIG_FILE = CONFIG_DIR / "config.json"


def load():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def save(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2))


def get_token():
    cfg = load()
    return cfg.get("token")


def get_host():
    cfg = load()
    return cfg.get("host")


def get_default_visibility():
    cfg = load()
    return cfg.get("default_visibility", "public")


def set_default_visibility(visibility):
    cfg = load()
    cfg["default_visibility"] = visibility
    save(cfg)


def save_credentials(host, token):
    cfg = load()
    cfg["host"] = host
    cfg["token"] = token
    save(cfg)
