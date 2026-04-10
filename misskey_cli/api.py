import uuid
import webbrowser

import requests

from . import config

PERMISSIONS = [
    "read:account",
    "write:notes",
    "read:notifications",
    "read:reactions",
    "write:reactions",
]


class MisskeyClient:
    def __init__(self):
        self.host = config.get_host()
        self.token = config.get_token()

    @property
    def logged_in(self):
        return self.host is not None and self.token is not None

    def _post(self, endpoint, **params):
        url = f"https://{self.host}/api/{endpoint}"
        body = {"i": self.token, **params}
        resp = requests.post(url, json=body, timeout=30)
        resp.raise_for_status()
        if resp.content:
            return resp.json()
        return None

    def login(self, host):
        session_id = str(uuid.uuid4())
        permissions = ",".join(PERMISSIONS)
        auth_url = f"https://{host}/miauth/{session_id}?name=misskey-cli&permission={permissions}"

        print(f"ブラウザで以下のURLを開いて認証してください:\n{auth_url}")
        try:
            webbrowser.open(auth_url)
        except Exception:
            pass

        input("\n認証が完了したらEnterを押してください...")

        resp = requests.post(f"https://{host}/api/miauth/{session_id}/check", json={}, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if not data.get("ok"):
            raise RuntimeError("認証に失敗しました")

        self.token = data["token"]
        self.host = host
        config.save_credentials(host, self.token)
        return data.get("user")

    def i(self):
        return self._post("i")

    def timeline(self, tl_type="home", limit=10):
        endpoints = {
            "home": "notes/timeline",
            "local": "notes/local-timeline",
            "hybrid": "notes/hybrid-timeline",
            "global": "notes/global-timeline",
        }
        endpoint = endpoints.get(tl_type)
        if not endpoint:
            raise ValueError(f"不明なタイムライン: {tl_type}")
        return self._post(endpoint, limit=limit)

    def create_note(self, text, visibility="public", cw=None, reply_id=None):
        params = {"text": text, "visibility": visibility}
        if cw:
            params["cw"] = cw
        if reply_id:
            params["replyId"] = reply_id
        return self._post("notes/create", **params)

    def renote(self, note_id):
        return self._post("notes/create", renoteId=note_id)

    def react(self, note_id, reaction):
        return self._post("notes/reactions/create", noteId=note_id, reaction=reaction)

    def notifications(self, limit=10):
        return self._post("i/notifications", limit=limit)
