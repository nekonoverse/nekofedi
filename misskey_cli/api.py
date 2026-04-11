import html
import re
import urllib.parse
import uuid
import webbrowser

import requests

from . import config
from .i18n import _

PERMISSIONS = [
    "read:account",
    "write:notes",
    "read:notifications",
    "read:reactions",
    "write:reactions",
]

MASTODON_SCOPES = "read write follow"
MASTODON_OOB_REDIRECT = "urn:ietf:wg:oauth:2.0:oob"

# Back-compat aliases (external code may still reference these).
NEKONOVERSE_SOFTWARE = "nekonoverse"
NEKONOVERSE_SCOPES = MASTODON_SCOPES
NEKONOVERSE_OOB_REDIRECT = MASTODON_OOB_REDIRECT

# Software families that speak MiAuth (Misskey-derived)
MIAUTH_SOFTWARE = {
    "misskey",
    "sharkey",
    "firefish",
    "iceshrimp",
    "iceshrimp-net",
    "cherrypick",
    "foundkey",
    "meisskey",
    "catodon",
    "magnetar",
}

# Software families that speak the Mastodon client API (login via OAuth OOB).
MASTODON_SOFTWARE = frozenset(
    {
        "mastodon",
        "fedibird",
        "pleroma",
        "akkoma",
        "gotosocial",
        "hometown",
        "nekonoverse",
    }
)

# Mastodon family members that support the Pleroma emoji-reaction extension
# (`PUT /api/v1/pleroma/statuses/:id/reactions/:emoji`).
_PLEROMA_REACTION_SOFTWARE = frozenset({"pleroma", "akkoma"})


def parse_host_arg(arg):
    """Parse a `login` argument into (host, scheme).

    Accepts ``host``, ``http://host[:port]`` or ``https://host[:port]``.
    Defaults to https when no scheme prefix is present.
    """
    s = arg.strip()
    if s.startswith("http://"):
        return s[len("http://"):].rstrip("/"), "http"
    if s.startswith("https://"):
        return s[len("https://"):].rstrip("/"), "https"
    return s.rstrip("/"), "https"


def detect_software(host, scheme="https"):
    """Discover server software via nodeinfo.

    Returns the lowercase software name (e.g. 'misskey', 'mastodon') or None
    if discovery fails. Applies a Fedibird fallback: some Fedibird instances
    self-report ``software.name == "mastodon"`` but leak ``fedibird`` in the
    version or repository URL.
    """
    try:
        r = requests.get(f"{scheme}://{host}/.well-known/nodeinfo", timeout=10)
        r.raise_for_status()
        links = r.json().get("links") or []
        if not links:
            return None
        # Prefer the highest-version link (last entry by convention).
        href = links[-1].get("href")
        if not href:
            return None
        # Mastodon-family instances hardcode https:// in the nodeinfo href
        # because Rails `url_for` uses ``force_ssl``. When the caller is
        # deliberately talking http (tests against a local proxy), keep the
        # request on the original scheme+host by using only the path.
        parsed = urllib.parse.urlparse(href)
        nodeinfo_url = f"{scheme}://{host}{parsed.path}" if parsed.path else href
        r = requests.get(nodeinfo_url, timeout=10)
        r.raise_for_status()
        sw = r.json().get("software") or {}
        name = (sw.get("name") or "").lower()
        if not name:
            return None
        if name == "mastodon":
            blob = f"{sw.get('version', '')} {sw.get('repository', '')}".lower()
            if "fedibird" in blob:
                return "fedibird"
        return name
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


class _BaseClient:
    """Shared host/token/scheme plumbing for both client implementations."""

    def __init__(self, host=None, token=None, scheme="https"):
        self.host = host
        self.token = token
        self.scheme = scheme

    @property
    def logged_in(self):
        return self.host is not None and self.token is not None

    def _url(self, path):
        return f"{self.scheme}://{self.host}/{path.lstrip('/')}"

    @staticmethod
    def _open_auth_url(url):
        print(_("auth.open_browser", url=url))
        try:
            webbrowser.open(url)
        except Exception:
            pass


class MisskeyClient(_BaseClient):
    def _post(self, endpoint, **params):
        body = {"i": self.token, **params}
        resp = requests.post(self._url(f"api/{endpoint}"), json=body, timeout=30)
        resp.raise_for_status()
        if resp.content:
            return resp.json()
        return None

    def login(self, host):
        self.host = host
        session_id = str(uuid.uuid4())
        permissions = ",".join(PERMISSIONS)
        auth_url = self._url(f"miauth/{session_id}?name=misskey-cli&permission={permissions}")

        self._open_auth_url(auth_url)

        input(_("auth.press_enter"))

        resp = requests.post(self._url(f"api/miauth/{session_id}/check"), json={}, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if not data.get("ok"):
            raise RuntimeError(_("auth.miauth_failed"))

        self.token = data["token"]
        self.host = host
        return data.get("user") or {}

    def i(self):
        return self._post("i")

    def timeline(self, tl_type="home", limit=10, list_id=None):
        if tl_type == "list":
            if not list_id:
                raise ValueError(_("error.list_id_required"))
            return self._post("notes/user-list-timeline", listId=list_id, limit=limit)
        endpoints = {
            "home": "notes/timeline",
            "local": "notes/local-timeline",
            "hybrid": "notes/hybrid-timeline",
            "global": "notes/global-timeline",
        }
        endpoint = endpoints.get(tl_type)
        if not endpoint:
            raise ValueError(_("error.unknown_timeline", tl_type=tl_type))
        return self._post(endpoint, limit=limit)

    def lists(self):
        """Return the user's lists as ``[{"id": ..., "name": ...}]``."""
        result = self._post("users/lists/list")
        return [
            {"id": lst.get("id"), "name": lst.get("name")}
            for lst in (result or [])
            if lst.get("id")
        ]

    def create_note(self, text, visibility="public", cw=None, reply_id=None, visible_user_ids=None):
        params = {"text": text, "visibility": visibility}
        if cw:
            params["cw"] = cw
        if reply_id:
            params["replyId"] = reply_id
        if visible_user_ids is not None:
            params["visibleUserIds"] = visible_user_ids
        return self._post("notes/create", **params)

    def show_note(self, note_id):
        return self._post("notes/show", noteId=note_id)

    def renote(self, note_id):
        return self._post("notes/create", renoteId=note_id)

    def react(self, note_id, reaction):
        return self._post("notes/reactions/create", noteId=note_id, reaction=reaction)

    def notifications(self, limit=10):
        return self._post("i/notifications", limit=limit)

    def emojis(self):
        resp = requests.post(self._url("api/emojis"), json={}, timeout=30)
        resp.raise_for_status()
        return resp.json().get("emojis", [])


class MastodonClient(_BaseClient):
    """Mastodon client API implementation.

    Drives Mastodon, Fedibird, Pleroma, Akkoma, GoToSocial, Hometown and
    Nekonoverse. Methods normalize Mastodon NoteResponse / Notification into
    Misskey-shaped dicts so the CLI's existing formatters and reply logic work
    unchanged. Per-software behaviour (emoji reactions) is dispatched on
    ``self.software``.
    """

    _VIS_OUT = {"home": "unlisted", "specified": "direct"}
    _VIS_IN = {"unlisted": "home", "direct": "specified"}
    # Detects a real `:shortcode:` (which Mastodon-family servers accept as-is)
    # so we can unwrap unicode emoji that the CLI wraps in colons before
    # handing it down.
    _SHORTCODE_RE = re.compile(r"^:([a-zA-Z0-9_]+)(?:@([a-zA-Z0-9.-]+))?:$")

    def __init__(self, host=None, token=None, scheme="https", software="mastodon"):
        super().__init__(host=host, token=token, scheme=scheme)
        self.software = software

    def _headers(self):
        h = {"Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _get(self, path, **params):
        resp = requests.get(self._url(path), params=params or None, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.json() if resp.content else None

    def _post(self, path, json=None, data=None):
        resp = requests.post(
            self._url(path),
            json=json,
            data=data,
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json() if resp.content else None

    def _put(self, path, json=None):
        resp = requests.put(
            self._url(path),
            json=json,
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json() if resp.content else None

    @classmethod
    def _unwrap_emoji(cls, reaction):
        """Strip the surrounding colons from a unicode-emoji reaction.

        The CLI auto-wraps every reaction in colons (``:foo:`` / ``:⭐:``).
        Mastodon-family servers expect real shortcodes wrapped in colons but
        unicode emoji bare, so unwrap anything that doesn't look like a
        shortcode.
        """
        if (
            len(reaction) >= 2
            and reaction.startswith(":")
            and reaction.endswith(":")
            and not cls._SHORTCODE_RE.match(reaction)
        ):
            return reaction[1:-1]
        return reaction

    # ----- Auth (OAuth OOB) -----

    def login(self, host):
        self.host = host
        # Step 1: register an app on the server.
        app_resp = requests.post(
            self._url("api/v1/apps"),
            json={
                "client_name": "misskey-cli",
                "redirect_uris": MASTODON_OOB_REDIRECT,
                "scopes": MASTODON_SCOPES,
            },
            timeout=30,
        )
        app_resp.raise_for_status()
        app = app_resp.json()
        client_id = app["client_id"]
        client_secret = app["client_secret"]

        # Step 2: open the OAuth authorize page.
        auth_url = self._url(
            "oauth/authorize?"
            + urllib.parse.urlencode(
                {
                    "response_type": "code",
                    "client_id": client_id,
                    "redirect_uri": MASTODON_OOB_REDIRECT,
                    "scope": MASTODON_SCOPES,
                }
            )
        )
        self._open_auth_url(auth_url)

        # Step 3: paste the OOB authorization code.
        code = input(_("auth.paste_code")).strip()
        if not code:
            raise RuntimeError(_("auth.code_missing"))

        # Step 4: exchange the code for an access token.
        token_resp = requests.post(
            self._url("oauth/token"),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": MASTODON_OOB_REDIRECT,
                "scope": MASTODON_SCOPES,
            },
            timeout=30,
        )
        token_resp.raise_for_status()
        self.token = token_resp.json()["access_token"]

        # Step 5: identify the user.
        me = self._get("api/v1/accounts/verify_credentials")
        return {
            "id": me.get("id"),
            "username": me.get("username"),
            "name": me.get("display_name") or me.get("username"),
        }

    # ----- API methods (normalized) -----

    def i(self):
        me = self._get("api/v1/accounts/verify_credentials")
        return {
            "id": me.get("id"),
            "username": me.get("username"),
            "name": me.get("display_name") or me.get("username"),
            "description": self._strip_html(me.get("note") or ""),
            "notesCount": me.get("statuses_count", 0),
            "followingCount": me.get("following_count", 0),
            "followersCount": me.get("followers_count", 0),
        }

    def timeline(self, tl_type="home", limit=10, list_id=None):
        # Fedibird reinterprets ``local=true`` as "local-only visibility" and
        # uses ``remote=false`` to mean "public timeline without remote posts".
        local_key = "remote" if self.software == "fedibird" else "local"
        local_val = "false" if self.software == "fedibird" else "true"
        if tl_type == "home":
            statuses = self._get("api/v1/timelines/home", limit=limit)
        elif tl_type == "local":
            statuses = self._get(
                "api/v1/timelines/public", **{local_key: local_val}, limit=limit
            )
        elif tl_type == "hybrid":
            # Mastodon has no hybrid timeline; fall back to local.
            statuses = self._get(
                "api/v1/timelines/public", **{local_key: local_val}, limit=limit
            )
        elif tl_type == "global":
            statuses = self._get("api/v1/timelines/public", limit=limit)
        elif tl_type == "list":
            if not list_id:
                raise ValueError(_("error.list_id_required"))
            statuses = self._get(f"api/v1/timelines/list/{list_id}", limit=limit)
        else:
            raise ValueError(_("error.unknown_timeline", tl_type=tl_type))
        return [self._normalize_note(s) for s in (statuses or [])]

    def lists(self):
        """Return the user's lists as ``[{"id": ..., "name": ...}]``.

        Mastodon exposes list names under ``title``; normalize to ``name``.
        """
        items = self._get("api/v1/lists")
        return [
            {"id": lst.get("id"), "name": lst.get("title") or lst.get("name")}
            for lst in (items or [])
            if lst.get("id")
        ]

    def create_note(self, text, visibility="public", cw=None, reply_id=None, visible_user_ids=None):
        body = {
            "status": text,
            "visibility": self._VIS_OUT.get(visibility, visibility),
        }
        if cw:
            body["spoiler_text"] = cw
        if reply_id:
            body["in_reply_to_id"] = reply_id
        # visible_user_ids is Misskey-only; Mastodon relies on @mentions in text.
        status = self._post("api/v1/statuses", json=body)
        return {"createdNote": self._normalize_note(status)} if status else None

    def show_note(self, note_id):
        s = self._get(f"api/v1/statuses/{note_id}")
        return self._normalize_note(s)

    def renote(self, note_id):
        s = self._post(f"api/v1/statuses/{note_id}/reblog")
        return self._normalize_note(s) if s else None

    def react(self, note_id, reaction):
        """React to a note. Dispatches on ``self.software``.

        Returns the parsed response on success. Returns ``None`` when the
        server has no emoji-reaction endpoint and we fall back to ``favourite``,
        so the CLI can surface that degradation to the user.
        """
        emoji = self._unwrap_emoji(reaction)
        encoded = urllib.parse.quote(emoji, safe="")
        if self.software in _PLEROMA_REACTION_SOFTWARE:
            return self._put(f"api/v1/pleroma/statuses/{note_id}/reactions/{encoded}")
        if self.software == "fedibird":
            # Fedibird exposes its own PUT /api/v1/statuses/:id/emoji_reactions/:emoji
            # (distinct from the Pleroma extension path, which it doesn't ship).
            return self._put(f"api/v1/statuses/{note_id}/emoji_reactions/{encoded}")
        if self.software == "nekonoverse":
            return self._post(f"api/v1/statuses/{note_id}/react/{encoded}")
        # mastodon / gotosocial / hometown: no custom emoji reactions.
        self._post(f"api/v1/statuses/{note_id}/favourite")
        return None

    def notifications(self, limit=10):
        notifs = self._get("api/v1/notifications", limit=limit)
        return [self._normalize_notif(n) for n in (notifs or [])]

    def emojis(self):
        emojis = self._get("api/v1/custom_emojis")
        return [{"name": e["shortcode"]} for e in (emojis or []) if e.get("shortcode")]

    # ----- Normalization helpers -----

    def _normalize_actor(self, actor):
        if not actor:
            return {}
        acct = actor.get("acct") or ""
        host = None
        if "@" in acct:
            _, _, host = acct.partition("@")
        return {
            "id": actor.get("id"),
            "username": actor.get("username"),
            "name": actor.get("display_name") or actor.get("username"),
            "host": host,
        }

    @staticmethod
    def _normalize_reactions(status):
        def collect(items):
            out = {}
            for r in items or []:
                name = r.get("name") or r.get("shortcode")
                if name:
                    out[name] = r.get("count", 0)
            return out

        # Fedibird-style emoji_reactions (preferred — preserves shortcodes),
        # Pleroma-style pleroma.emoji_reactions, Mastodon ReactionSummary.
        pleroma = (status.get("pleroma") or {}).get("emoji_reactions")
        return (
            collect(status.get("emoji_reactions"))
            or collect(pleroma)
            or collect(status.get("reactions"))
        )

    def _normalize_note(self, s):
        if not s:
            return None
        text = s.get("source")
        if not text:
            text = self._strip_html(s.get("content") or "")
        visibility = self._VIS_IN.get(s.get("visibility"), s.get("visibility") or "public")
        renote = None
        if s.get("reblog"):
            renote = self._normalize_note(s["reblog"])
        return {
            "id": s.get("id"),
            "createdAt": s.get("published") or s.get("created_at"),
            "user": self._normalize_actor(s.get("account") or s.get("actor")),
            "text": text,
            "cw": s.get("spoiler_text") or None,
            "visibility": visibility,
            "renote": renote,
            "reactions": self._normalize_reactions(s),
            "visibleUserIds": [],
        }

    def _normalize_notif(self, n):
        type_map = {
            "reblog": "renote",
            "favourite": "reaction",
            "pleroma:emoji_reaction": "reaction",
        }
        raw_type = n.get("type")
        reaction = None
        if raw_type == "favourite":
            reaction = "⭐"
        elif raw_type == "reaction":
            # Nekonoverse-style emoji reaction notification.
            emoji = n.get("emoji") or {}
            reaction = (emoji.get("shortcode") and f":{emoji['shortcode']}:") or n.get("emoji_name") or "⭐"
        elif raw_type == "pleroma:emoji_reaction":
            # Pleroma/Fedibird: {"emoji": "🎉"} for unicode,
            # {"emoji": ":shortcode:"} for custom (already colon-wrapped).
            raw = n.get("emoji") or n.get("name") or "⭐"
            if isinstance(raw, dict):
                # Defensive: some implementations embed a dict.
                raw = raw.get("shortcode") or raw.get("name") or "⭐"
                raw = f":{raw}:" if raw and not raw.startswith(":") else raw
            reaction = raw
        return {
            "type": type_map.get(raw_type, raw_type),
            "createdAt": n.get("created_at"),
            "user": self._normalize_actor(n.get("account")),
            "note": self._normalize_note(n.get("status")) if n.get("status") else None,
            "reaction": reaction,
        }

    _RE_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
    _RE_PARA_BREAK = re.compile(r"</p>\s*<p[^>]*>", re.IGNORECASE)
    _RE_P_OPEN = re.compile(r"<p[^>]*>", re.IGNORECASE)
    _RE_P_CLOSE = re.compile(r"</p>", re.IGNORECASE)
    _RE_TAG = re.compile(r"<[^>]+>")

    @classmethod
    def _strip_html(cls, s):
        if not s:
            return ""
        # Convert paragraph and break tags to plain newlines first.
        s = cls._RE_BR.sub("\n", s)
        s = cls._RE_PARA_BREAK.sub("\n\n", s)
        s = cls._RE_P_OPEN.sub("", s)
        s = cls._RE_P_CLOSE.sub("", s)
        # Drop any remaining tags.
        s = cls._RE_TAG.sub("", s)
        return html.unescape(s).strip()


# Back-compat alias so `from misskey_cli.api import NekonoverseClient` keeps
# working (existing tests and any external callers).
NekonoverseClient = MastodonClient


def make_client(host=None, token=None, software=None, scheme=None):
    """Build the appropriate client for the active (or given) account.

    When ``software`` is provided explicitly (e.g. during ``cmd_login``),
    no fields are auto-loaded from the active account. Otherwise the active
    account is fetched once and any unspecified fields default to it.
    """
    if software is None:
        acct = config.get_active_account()
        if acct:
            if host is None:
                host = acct.host
            if token is None:
                token = acct.token
            software = acct.software
            if scheme is None:
                scheme = acct.scheme
    if scheme is None:
        scheme = "https"
    if software in MASTODON_SOFTWARE:
        return MastodonClient(host=host, token=token, scheme=scheme, software=software)
    return MisskeyClient(host=host, token=token, scheme=scheme)
