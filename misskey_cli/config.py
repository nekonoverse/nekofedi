import os
from pathlib import Path


CONFIG_DIR = Path(os.environ.get("MISSKEY_CLI_CONFIG_DIR", Path.home() / ".config" / "misskey-cli"))
DB_PATH = CONFIG_DIR / "config.db"


def _get_settings():
    from .db import get_session, Settings
    with get_session() as s:
        row = s.query(Settings).first()
        if not row:
            row = Settings(default_visibility="public")
            s.add(row)
            s.commit()
            s.refresh(row)
        return row


def get_active_account():
    from .db import get_session, Account
    with get_session() as s:
        return s.query(Account).filter_by(active=True).first()


def get_host():
    acct = get_active_account()
    return acct.host if acct else None


def get_token():
    acct = get_active_account()
    return acct.token if acct else None


def get_default_visibility():
    from .db import get_session, Settings
    with get_session() as s:
        row = s.query(Settings).first()
        return row.default_visibility if row else "public"


def get_default_timeline():
    from .db import get_session, Settings
    with get_session() as s:
        row = s.query(Settings).first()
        return row.default_timeline if row else "home"


def set_default_timeline(timeline):
    from .db import get_session, Settings
    with get_session() as s:
        row = s.query(Settings).first()
        if row:
            row.default_timeline = timeline
        else:
            s.add(Settings(default_timeline=timeline))
        s.commit()


def set_default_visibility(visibility):
    from .db import get_session, Settings
    with get_session() as s:
        row = s.query(Settings).first()
        if row:
            row.default_visibility = visibility
        else:
            s.add(Settings(default_visibility=visibility))
        s.commit()


def save_credentials(host, token, username=None):
    from .db import get_session, Account
    with get_session() as s:
        # deactivate all
        s.query(Account).update({"active": False})
        # upsert by host+token
        acct = s.query(Account).filter_by(host=host).first()
        if acct:
            acct.token = token
            acct.username = username
            acct.active = True
        else:
            s.add(Account(host=host, token=token, username=username, active=True))
        s.commit()
