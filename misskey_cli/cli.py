import atexit
import cmd
import os
import readline
import subprocess
import tempfile

from .api import MisskeyClient
from . import config

HISTORY_FILE = config.CONFIG_DIR / "history"

VISIBILITIES = ("public", "home", "followers", "specified")


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


class MisskeyCLI(cmd.Cmd):
    intro = "Misskey CLI - 'help' でコマンド一覧、'quit' で終了"

    def __init__(self):
        super().__init__()
        self._init_history()
        self.username = None
        self.client = MisskeyClient()
        if self.client.logged_in:
            try:
                me = self.client.i()
                self.username = me["username"]
                print(f"{me.get('name') or me['username']} としてログイン中")
            except Exception:
                print("保存済みトークンが無効です。'login' で再認証してください。")
                self.client.token = None
        self._update_prompt()

    def _init_history(self):
        config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            readline.read_history_file(HISTORY_FILE)
        except FileNotFoundError:
            pass
        readline.set_history_length(1000)
        atexit.register(readline.write_history_file, HISTORY_FILE)

    def _update_prompt(self):
        dim = "\001\033[2m\002"
        reset = "\001\033[0m\002"
        if self.username and self.client.host:
            who = f"@{self.username}{dim}@{self.client.host}{reset}"
        else:
            who = "(no login)"
        vis = config.get_default_visibility()
        self.prompt = f"{who} [{vis}]> "

    def _require_login(self):
        if not self.client.logged_in:
            print("先に 'login <host>' でログインしてください。")
            return False
        return True

    def do_login(self, arg):
        """login <host> - インスタンスにログイン"""
        host = arg.strip()
        if not host:
            print("使い方: login <host>  例: login misskey.caligula-sea.net")
            return
        try:
            user = self.client.login(host)
            name = user.get("name") or user["username"]
            self.username = user["username"]
            self._update_prompt()
            print(f"ログイン成功: {name}")
        except Exception as e:
            print(f"ログイン失敗: {e}")

    def do_i(self, arg):
        """自分のプロフィールを表示"""
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

    def do_tl(self, arg):
        """tl [home|local|hybrid|global] [件数] - タイムライン表示"""
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

    def _resolve_visibility(self, arg):
        if arg and arg in VISIBILITIES:
            return arg
        return config.get_default_visibility()

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

    def do_note(self, arg):
        """note [visibility] - nvim でノートを書いて投稿 (visibility: public/home/followers/specified)"""
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

    def do_note_text(self, arg):
        """note_text [visibility] <text> - テキストを直接指定してノート投稿"""
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

    def do_default_visibility(self, arg):
        """default_visibility [visibility] - デフォルト公開範囲を設定/確認"""
        v = arg.strip()
        if not v:
            print(f"現在のデフォルト: {config.get_default_visibility()}")
            return
        if v not in VISIBILITIES:
            print(f"不正な値です。選択肢: {', '.join(VISIBILITIES)}")
            return
        config.set_default_visibility(v)
        self._update_prompt()
        print(f"デフォルト公開範囲を '{v}' に設定しました")

    def do_reply(self, arg):
        """reply <note_id> <text> - リプライ"""
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

    def do_renote(self, arg):
        """renote <note_id> - リノート"""
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

    def do_react(self, arg):
        """react <note_id> <emoji> - リアクション (例: react abc123 👍)"""
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

    def do_notif(self, arg):
        """notif [件数] - 通知一覧"""
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

    def do_quit(self, arg):
        """終了"""
        print("bye")
        return True

    do_exit = do_quit
    do_EOF = do_quit

    def emptyline(self):
        pass
