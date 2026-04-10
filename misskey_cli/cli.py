import os
import subprocess
import tempfile

from prompt_toolkit import PromptSession, print_formatted_text, HTML
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory

from .api import MisskeyClient
from . import config

HISTORY_FILE = str(config.CONFIG_DIR / "history")

VISIBILITIES = ("public", "home", "followers", "specified")
TL_TYPES = ("home", "local", "hybrid", "global")

COMMANDS = {
    "login": "login <host> - インスタンスにログイン",
    "i": "自分のプロフィール表示",
    "tl": "tl [home|local|hybrid|global] [件数] - タイムライン表示",
    "note": "note [visibility] - nvim でノート作成",
    "note_text": "note_text [visibility] <text> - テキスト直接指定でノート投稿",
    "default_visibility": "default_visibility [visibility] - デフォルト公開範囲",
    "reply": "reply <note_id> <text> - リプライ",
    "renote": "renote <note_id> - リノート",
    "react": "react <note_id> <emoji> - リアクション",
    "notif": "notif [件数] - 通知一覧",
    "help": "コマンド一覧を表示",
    "quit": "終了",
    "exit": "終了",
}


def _format_note(note):
    user = note.get("user", {})
    name = user.get("name") or user.get("username", "???")
    username = user.get("username", "???")
    host = user.get("host")
    acct = f"@{username}@{host}" if host else f"@{username}"
    ts = note.get("createdAt", "")[:19].replace("T", " ")
    note_id = note.get("id", "")

    lines = [f"  {name} ({acct})  {ts}  [{note_id}]"]

    cw = note.get("cw")
    if cw:
        lines.append(f"  CW: {cw}")

    text = note.get("text")
    if text:
        for line in text.split("\n"):
            lines.append(f"  {line}")

    renote = note.get("renote")
    if renote and not text:
        lines.append(f"  RN -> {_format_note(renote)}")

    reactions = note.get("reactions", {})
    if reactions:
        r_str = " ".join(f"{k}{v}" for k, v in reactions.items())
        lines.append(f"  {r_str}")

    return "\n".join(lines)


def _format_notification(notif):
    ntype = notif.get("type", "unknown")
    user = notif.get("user", {})
    name = user.get("name") or user.get("username", "???")
    ts = notif.get("createdAt", "")[:19].replace("T", " ")

    if ntype == "reaction":
        reaction = notif.get("reaction", "?")
        note_text = (notif.get("note", {}).get("text") or "")[:40]
        return f"  [{ts}] {reaction} {name} -> {note_text}"
    elif ntype == "reply":
        text = (notif.get("note", {}).get("text") or "")[:60]
        return f"  [{ts}] reply {name}: {text}"
    elif ntype == "renote":
        return f"  [{ts}] renote {name}"
    elif ntype == "follow":
        return f"  [{ts}] follow {name}"
    elif ntype == "mention":
        text = (notif.get("note", {}).get("text") or "")[:60]
        return f"  [{ts}] mention {name}: {text}"
    elif ntype == "quote":
        text = (notif.get("note", {}).get("text") or "")[:60]
        return f"  [{ts}] quote {name}: {text}"
    else:
        return f"  [{ts}] {ntype} {name}"


class MisskeyCompleter(Completer):
    def __init__(self, get_emoji_shortcodes):
        self._get_emoji_shortcodes = get_emoji_shortcodes

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        parts = text.split()

        if not parts or (len(parts) == 1 and not text.endswith(" ")):
            # Completing command name
            word = parts[0] if parts else ""
            for cmd_name, desc in COMMANDS.items():
                if cmd_name.startswith(word):
                    yield Completion(cmd_name, start_position=-len(word), display_meta=desc)
            return

        cmd = parts[0]
        # Current word being typed (empty if trailing space)
        current = parts[-1] if not text.endswith(" ") else ""

        if cmd == "tl" and len(parts) <= 2:
            for t in TL_TYPES:
                if t.startswith(current):
                    yield Completion(t, start_position=-len(current))

        elif cmd in ("note", "note_text", "default_visibility") and len(parts) <= 2:
            for v in VISIBILITIES:
                if v.startswith(current):
                    yield Completion(v, start_position=-len(current))

        elif cmd == "react" and len(parts) >= 2:
            # Second arg onwards: emoji shortcodes
            arg_count = len(parts) - 1 if text.endswith(" ") else len(parts) - 1
            if arg_count >= 1:
                for code in self._get_emoji_shortcodes():
                    if code.startswith(current):
                        yield Completion(code, start_position=-len(current))


class MisskeyCLI:
    def __init__(self):
        self.username = None
        self._emoji_cache = None
        self.client = MisskeyClient()
        if self.client.logged_in:
            try:
                me = self.client.i()
                self.username = me["username"]
                print(f"{me.get('name') or me['username']} としてログイン中")
            except Exception:
                print("保存済みトークンが無効です。'login' で再認証してください。")
                self.client.token = None

        config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.session = PromptSession(
            history=FileHistory(HISTORY_FILE),
            completer=MisskeyCompleter(self._get_emoji_shortcodes),
        )

    def _get_emoji_shortcodes(self):
        if self._emoji_cache is None and self.client.logged_in:
            try:
                emojis = self.client.emojis()
                self._emoji_cache = [f":{e['name']}:" for e in emojis]
            except Exception:
                self._emoji_cache = []
        return self._emoji_cache or []

    def _get_prompt(self):
        if self.username and self.client.host:
            who = [("", f"@{self.username}"), ("ansibrightblack", f"@{self.client.host}")]
        else:
            who = [("", "(no login)")]
        vis = config.get_default_visibility()
        who.append(("", f" [{vis}]> "))
        return who

    def _require_login(self):
        if not self.client.logged_in:
            print("先に 'login <host>' でログインしてください。")
            return False
        return True

    def _edit_text(self):
        editor = os.environ.get("EDITOR", "nvim")
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w+", delete=False) as f:
            tmppath = f.name
        try:
            subprocess.call([editor, tmppath])
            with open(tmppath) as f:
                text = f.read().strip()
            return text or None
        finally:
            os.unlink(tmppath)

    def _resolve_visibility(self, arg):
        if arg and arg in VISIBILITIES:
            return arg
        return config.get_default_visibility()

    def cmd_help(self, arg):
        for name, desc in COMMANDS.items():
            print(f"  {name:22s} {desc}")

    def cmd_login(self, arg):
        host = arg.strip()
        if not host:
            print("使い方: login <host>  例: login misskey.caligula-sea.net")
            return
        try:
            user = self.client.login(host)
            name = user.get("name") or user["username"]
            self.username = user["username"]
            print(f"ログイン成功: {name}")
        except Exception as e:
            print(f"ログイン失敗: {e}")

    def cmd_i(self, arg):
        if not self._require_login():
            return
        try:
            me = self.client.i()
            name = me.get("name") or me["username"]
            print(f"  {name} (@{me['username']})")
            if me.get("description"):
                print(f"  {me['description']}")
            print(f"  notes: {me.get('notesCount', 0)}  following: {me.get('followingCount', 0)}  followers: {me.get('followersCount', 0)}")
        except Exception as e:
            print(f"エラー: {e}")

    def cmd_tl(self, arg):
        if not self._require_login():
            return
        parts = arg.strip().split()
        tl_type = parts[0] if parts else "home"
        limit = int(parts[1]) if len(parts) > 1 else 10
        try:
            notes = self.client.timeline(tl_type, limit)
            if not notes:
                print("ノートがありません。")
                return
            for note in reversed(notes):
                print(_format_note(note))
                print()
        except Exception as e:
            print(f"エラー: {e}")

    def cmd_note(self, arg):
        if not self._require_login():
            return
        visibility = self._resolve_visibility(arg.strip())
        text = self._edit_text()
        if not text:
            print("空のノートは投稿しません。")
            return
        try:
            result = self.client.create_note(text, visibility=visibility)
            note = result["createdNote"]
            print(f"投稿しました [{note['id']}] ({visibility})")
        except Exception as e:
            print(f"エラー: {e}")

    def cmd_note_text(self, arg):
        if not self._require_login():
            return
        parts = arg.strip().split(None, 1)
        if not parts:
            print("使い方: note_text [visibility] <text>")
            return
        if parts[0] in VISIBILITIES:
            visibility = parts[0]
            text = parts[1] if len(parts) > 1 else ""
        else:
            visibility = config.get_default_visibility()
            text = arg.strip()
        if not text:
            print("使い方: note_text [visibility] <text>")
            return
        try:
            result = self.client.create_note(text, visibility=visibility)
            note = result["createdNote"]
            print(f"投稿しました [{note['id']}] ({visibility})")
        except Exception as e:
            print(f"エラー: {e}")

    def cmd_default_visibility(self, arg):
        v = arg.strip()
        if not v:
            print(f"現在のデフォルト: {config.get_default_visibility()}")
            return
        if v not in VISIBILITIES:
            print(f"不正な値です。選択肢: {', '.join(VISIBILITIES)}")
            return
        config.set_default_visibility(v)
        print(f"デフォルト公開範囲を '{v}' に設定しました")

    def cmd_reply(self, arg):
        if not self._require_login():
            return
        parts = arg.strip().split(None, 1)
        if len(parts) < 2:
            print("使い方: reply <note_id> <text>")
            return
        note_id, text = parts
        try:
            result = self.client.create_note(text, reply_id=note_id)
            note = result["createdNote"]
            print(f"リプライしました [{note['id']}]")
        except Exception as e:
            print(f"エラー: {e}")

    def cmd_renote(self, arg):
        if not self._require_login():
            return
        note_id = arg.strip()
        if not note_id:
            print("使い方: renote <note_id>")
            return
        try:
            self.client.renote(note_id)
            print("リノートしました")
        except Exception as e:
            print(f"エラー: {e}")

    def cmd_react(self, arg):
        if not self._require_login():
            return
        parts = arg.strip().split(None, 1)
        if len(parts) < 2:
            print("使い方: react <note_id> <emoji>")
            return
        note_id, reaction = parts
        try:
            self.client.react(note_id, reaction)
            print(f"リアクションしました {reaction}")
        except Exception as e:
            print(f"エラー: {e}")

    def cmd_notif(self, arg):
        if not self._require_login():
            return
        limit = int(arg.strip()) if arg.strip() else 10
        try:
            notifs = self.client.notifications(limit)
            if not notifs:
                print("通知はありません。")
                return
            for n in notifs:
                print(_format_notification(n))
        except Exception as e:
            print(f"エラー: {e}")

    def cmdloop(self):
        print("Misskey CLI - 'help' でコマンド一覧、'quit' で終了")
        dispatch = {
            "login": self.cmd_login,
            "i": self.cmd_i,
            "tl": self.cmd_tl,
            "note": self.cmd_note,
            "note_text": self.cmd_note_text,
            "default_visibility": self.cmd_default_visibility,
            "reply": self.cmd_reply,
            "renote": self.cmd_renote,
            "react": self.cmd_react,
            "notif": self.cmd_notif,
            "help": self.cmd_help,
            "quit": None,
            "exit": None,
        }

        while True:
            try:
                text = self.session.prompt(self._get_prompt()).strip()
            except (EOFError, KeyboardInterrupt):
                print("bye")
                break

            if not text:
                continue

            parts = text.split(None, 1)
            cmd_name = parts[0]
            arg = parts[1] if len(parts) > 1 else ""

            if cmd_name in ("quit", "exit"):
                print("bye")
                break

            handler = dispatch.get(cmd_name)
            if handler:
                handler(arg)
            else:
                print(f"不明なコマンド: {cmd_name} ('help' で一覧表示)")
