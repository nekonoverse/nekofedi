import os
from pathlib import Path


CONFIG_DIR = Path(os.environ.get("MISSKEY_CLI_CONFIG_DIR", Path.home() / ".config" / "misskey-cli"))
DB_PATH = CONFIG_DIR / "config.db"


def get_active_account():
    from .db import get_session, Account
    with get_session() as s:
        return s.query(Account).filter_by(active=True).first()


def list_accounts():
    from .db import get_session, Account
    with get_session() as s:
        return [
            {
                "id": a.id,
                "host": a.host,
                "username": a.username,
                "active": bool(a.active),
                "software": a.software,
                "scheme": a.scheme,
            }
            for a in s.query(Account).order_by(Account.id).all()
        ]


def _parse_acct(acct):
    """Parse '@user@host' or 'user@host' or 'host' into (username, host).

    Returns (username, host) where either may be None when not specified.
    """
    s = acct.lstrip("@")
    if "@" in s:
        username, host = s.split("@", 1)
        return username or None, host or None
    # Ambiguous: could be a bare host or a bare username.
    # If the original started with '@', treat it as a username.
    if acct.startswith("@"):
        return s, None
    return None, s


def switch_account(acct):
    """Switch active account by '@user@host' or 'host'.

    Returns one of: 'ok', 'not_found', 'ambiguous'.
    """
    from .db import get_session, Account
    username, host = _parse_acct(acct)
    with get_session() as s:
        q = s.query(Account)
        if username is not None:
            q = q.filter_by(username=username)
        if host is not None:
            q = q.filter_by(host=host)
        matches = q.all()
        if not matches:
            return "not_found"
        if len(matches) > 1:
            return "ambiguous"
        s.query(Account).update({"active": False})
        matches[0].active = True
        s.commit()
        return "ok"


def delete_active_account():
    from .db import get_session, Account
    with get_session() as s:
        acct = s.query(Account).filter_by(active=True).first()
        if not acct:
            return False
        s.delete(acct)
        s.commit()
        return True


def get_default_visibility():
    """Return the active account's default visibility, or 'public' if none."""
    acct = get_active_account()
    return acct.default_visibility if acct else "public"


def get_default_timeline():
    """Return the active account's default timeline, or 'home' if none."""
    acct = get_active_account()
    return acct.default_timeline if acct else "home"


def set_default_visibility(visibility):
    """Persist the default visibility on the active account.

    Returns True on success, False if no account is active.
    """
    from .db import get_session, Account
    with get_session() as s:
        acct = s.query(Account).filter_by(active=True).first()
        if not acct:
            return False
        acct.default_visibility = visibility
        s.commit()
        return True


def set_default_timeline(timeline):
    """Persist the default timeline on the active account.

    Returns True on success, False if no account is active.
    """
    from .db import get_session, Account
    with get_session() as s:
        acct = s.query(Account).filter_by(active=True).first()
        if not acct:
            return False
        acct.default_timeline = timeline
        s.commit()
        return True


def get_active_list_id():
    """Return the active account's currently selected list id, or None."""
    acct = get_active_account()
    return acct.active_list_id if acct else None


def set_active_list_id(list_id):
    """Persist the selected list id on the active account.

    Pass ``None`` to clear. Returns True on success, False if no account
    is active.
    """
    from .db import get_session, Account
    with get_session() as s:
        acct = s.query(Account).filter_by(active=True).first()
        if not acct:
            return False
        acct.active_list_id = list_id
        s.commit()
        return True


def get_app_config(key, default=None):
    """Read a value from the global app_config key/value table."""
    from .db import get_session, AppConfig
    with get_session() as s:
        row = s.query(AppConfig).filter_by(key=key).first()
        return row.value if row else default


def set_app_config(key, value):
    """Upsert a value into the global app_config key/value table."""
    from .db import get_session, AppConfig
    with get_session() as s:
        row = s.query(AppConfig).filter_by(key=key).first()
        if row:
            row.value = value
        else:
            s.add(AppConfig(key=key, value=value))
        s.commit()


def save_credentials(host, token, username=None, software=None, scheme=None):
    from .db import get_session, Account
    with get_session() as s:
        # deactivate all
        s.query(Account).update({"active": False})
        # Upsert by (host, username) to allow multiple accounts per host.
        acct = None
        if username:
            acct = s.query(Account).filter_by(host=host, username=username).first()
            if not acct:
                # Adopt a legacy row that had no username persisted yet.
                acct = s.query(Account).filter_by(host=host, username=None).first()
        else:
            acct = s.query(Account).filter_by(host=host).first()
        if acct:
            acct.token = token
            if username:
                acct.username = username
            if software is not None:
                acct.software = software
            if scheme is not None:
                acct.scheme = scheme
            acct.active = True
        else:
            s.add(Account(
                host=host,
                token=token,
                username=username,
                active=True,
                software=software,
                scheme=scheme,
            ))
        s.commit()
