import os
import re
import subprocess
import tempfile
from datetime import datetime

from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory

from .api import MisskeyClient
from . import config

HISTORY_FILE = str(config.CONFIG_DIR / "history")

VISIBILITIES = ("public", "home", "followers", "specified")
# Wider to narrower
VISIBILITY_RANK = {"public": 0, "home": 1, "followers": 2, "specified": 3}


def _narrower_visibility(a, b):
    return a if VISIBILITY_RANK.get(a, 0) >= VISIBILITY_RANK.get(b, 0) else b
TL_TYPES = ("home", "local", "hybrid", "global")

COMMANDS = {
    "login": "login <host> - インスタンスにログイン",
    "account": "account [use <host>] - アカウント一覧 / 切替",
    "logout": "アクティブなアカウントを削除",
    "i": "自分のプロフィール表示",
    "tl": "tl [home|local|hybrid|global] [件数] - タイムライン表示",
    "note": "note [visibility] - nvim でノート作成",
    "note_text": "note_text [visibility] <text> - テキスト直接指定でノート投稿",
    "default_visibility": "default_visibility [visibility] - デフォルト公開範囲",
    "default_timeline": "default_timeline [home|local|hybrid|global] - デフォルトTL",
    "reply": "reply <note_id> [visibility] - エディタでリプライ作成",
    "reply_text": "reply_text <note_id> [visibility] <text> - テキスト直接指定でリプライ",
    "renote": "renote <note_id> - リノート",
    "react": "react <note_id> <emoji> - リアクション",
    "notif": "notif [件数] - 通知一覧",
    "help": "コマンド一覧を表示",
    "quit": "終了",
    "exit": "終了",
}


def _format_ts(iso_str):
    """Convert ISO 8601 UTC timestamp to local time string (honors TZ env var)."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return iso_str[:19].replace("T", " ")


def _format_note(note):
    user = note.get("user", {})
    name = user.get("name") or user.get("username", "???")
    username = user.get("username", "???")
    host = user.get("host")
    acct = f"@{username}@{host}" if host else f"@{username}"
    ts = _format_ts(note.get("createdAt", ""))
    note_id = note.get("id", "")

    parts = [
        ("bold", f"  {name} "),
        ("ansibrightblack", f"({acct})  {ts}  "),
        ("ansicyan", f"[{note_id}]"),
        ("", "\n"),
    ]

    cw = note.get("cw")
    if cw:
        parts.append(("ansiyellow", f"  CW: {cw}\n"))

    text = note.get("text")
    if text:
        for line in text.split("\n"):
            parts.append(("", f"  {line}\n"))

    renote = note.get("renote")
    if renote and not text:
        parts.append(("ansimagenta", "  RN -> "))
        parts.extend(_format_note(renote))

    reactions = note.get("reactions", {})
    if reactions:
        r_str = " ".join(f"{k}{v}" for k, v in reactions.items())
        parts.append(("ansigreen", f"  {r_str}\n"))

    return parts


def _format_notification(notif):
    ntype = notif.get("type", "unknown")
    user = notif.get("user", {})
    name = user.get("name") or user.get("username", "???")
    ts = _format_ts(notif.get("createdAt", ""))

    parts = [("ansibrightblack", f"  [{ts}] ")]

    if ntype == "reaction":
        reaction = notif.get("reaction", "?")
        note_text = (notif.get("note", {}).get("text") or "")[:40]
        parts.append(("ansicyan", "reaction "))
        parts.append(("", f"{reaction} "))
        parts.append(("bold", f"{name} "))
        parts.append(("", f"-> {note_text}"))
    elif ntype == "reply":
        text = (notif.get("note", {}).get("text") or "")[:60]
        parts.append(("ansicyan", "reply "))
        parts.append(("bold", f"{name}: "))
        parts.append(("", text))
    elif ntype == "renote":
        parts.append(("ansicyan", "renote "))
        parts.append(("bold", name))
    elif ntype == "follow":
        parts.append(("ansicyan", "follow "))
        parts.append(("bold", name))
    elif ntype == "mention":
        text = (notif.get("note", {}).get("text") or "")[:60]
        parts.append(("ansicyan", "mention "))
        parts.append(("bold", f"{name}: "))
        parts.append(("", text))
    elif ntype == "quote":
        text = (notif.get("note", {}).get("text") or "")[:60]
        parts.append(("ansicyan", "quote "))
        parts.append(("bold", f"{name}: "))
        parts.append(("", text))
    else:
        parts.append(("ansicyan", f"{ntype} "))
        parts.append(("bold", name))

    parts.append(("", "\n"))
    return parts


NOTE_ID_COMMANDS = ("reply", "reply_text", "renote", "react")


LUA_EMOJI_COMPLETE = r"""
local emojis = __EMOJIS__

local function trigger()
  if vim.fn.mode() ~= 'i' then return end
  local line = vim.api.nvim_get_current_line()
  local col = vim.api.nvim_win_get_cursor(0)[2]
  local before = line:sub(1, col)
  local colon_pos = before:find(':[%w_-]*$')
  if not colon_pos then return end
  -- Skip if ':' is preceded by a word/identifier char (e.g. URLs, closing colon of an emoji)
  if colon_pos > 1 then
    local prev = before:sub(colon_pos - 1, colon_pos - 1)
    if prev:match('[%w_-]') then return end
  end
  local needle = before:sub(colon_pos + 1):lower()
  local matches = {}
  for _, e in ipairs(emojis) do
    local bare = e:sub(2, -2):lower()
    if needle == '' or bare:find(needle, 1, true) then
      table.insert(matches, e)
    end
  end
  if #matches > 0 then
    vim.fn.complete(colon_pos, matches)
  end
end

vim.api.nvim_create_autocmd({'TextChangedI', 'TextChangedP'}, {
  buffer = 0,
  callback = trigger,
})

vim.opt.completeopt = 'menu,menuone,noinsert,noselect'
"""


def _build_emoji_lua(shortcodes):
    safe = [n for n in shortcodes if re.match(r'^[a-zA-Z0-9_-]+$', n)]
    emoji_list = "{" + ", ".join(f"':{n}:'" for n in safe) + "}"
    return LUA_EMOJI_COMPLETE.replace("__EMOJIS__", emoji_list)


def _note_summary(note):
    """Extract id, username and short text snippet from a note dict."""
    user = note.get("user", {})
    username = user.get("username", "???")
    text = note.get("text") or ""
    if not text and note.get("renote"):
        text = "RN: " + (note["renote"].get("text") or "")
    if not text and note.get("cw"):
        text = f"CW: {note['cw']}"
    snippet = text[:40].replace("\n", " ")
    return note.get("id", ""), username, snippet


class MisskeyCompleter(Completer):
    def __init__(self, get_emoji_names, get_note_meta):
        self._get_emoji_names = get_emoji_names
        self._get_note_meta = get_note_meta

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
        # Position of the current/next argument (1 = first arg)
        arg_pos = len(parts) if text.endswith(" ") else len(parts) - 1

        # Note ID completion (first arg of reply/renote/react)
        if cmd in NOTE_ID_COMMANDS and arg_pos == 1:
            for meta in self._get_note_meta():
                nid = meta["id"]
                if nid.startswith(current):
                    display_meta = f"@{meta['username']}: {meta['snippet']}"
                    yield Completion(nid, start_position=-len(current), display_meta=display_meta)
            return

        if cmd == "tl" and len(parts) <= 2:
            for t in TL_TYPES:
                if t.startswith(current):
                    yield Completion(t, start_position=-len(current))

        elif cmd == "default_timeline" and len(parts) <= 2:
            for t in TL_TYPES:
                if t.startswith(current):
                    yield Completion(t, start_position=-len(current))

        elif cmd in ("note", "note_text", "default_visibility") and len(parts) <= 2:
            for v in VISIBILITIES:
                if v.startswith(current):
                    yield Completion(v, start_position=-len(current))

        elif cmd in ("reply", "reply_text") and arg_pos == 2:
            for v in VISIBILITIES:
                if v.startswith(current):
                    yield Completion(v, start_position=-len(current))

        elif cmd == "react" and arg_pos == 2:
            # Emoji name completion (substring match)
            current_lower = current.lower()
            for name in self._get_emoji_names():
                if current_lower in name.lower():
                    yield Completion(name, start_position=-len(current))

        elif cmd == "account":
            if arg_pos == 1:
                for sub in ("use",):
                    if sub.startswith(current):
                        yield Completion(sub, start_position=-len(current))
            elif arg_pos == 2 and len(parts) >= 2 and parts[1] == "use":
                for a in config.list_accounts():
                    if a["username"]:
                        acct = f"@{a['username']}@{a['host']}"
                    else:
                        acct = a["host"]
                    if acct.startswith(current):
                        meta = "(active)" if a["active"] else ""
                        yield Completion(acct, start_position=-len(current), display_meta=meta)


class MisskeyCLI:
    def __init__(self):
        self.username = None
        self.user_id = None
        self._emoji_cache = None
        self._note_meta = []
        self.client = MisskeyClient()
        if self.client.logged_in:
            try:
                me = self.client.i()
                self.username = me["username"]
                self.user_id = me["id"]
                print(f"{me.get('name') or me['username']} としてログイン中")
            except Exception:
                print("保存済みトークンが無効です。'login' で再認証してください。")
                self.client.token = None

        config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.session = PromptSession(
            history=FileHistory(HISTORY_FILE),
            completer=MisskeyCompleter(self._get_emoji_names, self._get_note_meta),
        )

    def _get_emoji_names(self):
        if self._emoji_cache is None and self.client.logged_in:
            try:
                emojis = self.client.emojis()
                self._emoji_cache = [e['name'] for e in emojis]
            except Exception:
                self._emoji_cache = []
        return self._emoji_cache or []

    def _get_note_meta(self):
        return self._note_meta

    def _collect_notes(self, notes):
        """Add note metadata to cache (most recent first, deduped)."""
        seen = {m["id"] for m in self._note_meta}
        new_meta = []
        for note in notes:
            nid, username, snippet = _note_summary(note)
            if nid and nid not in seen:
                new_meta.append({"id": nid, "username": username, "snippet": snippet})
                seen.add(nid)
        self._note_meta = new_meta + self._note_meta

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

    def _edit_text(self, initial=""):
        editor = os.environ.get("EDITOR", "nvim")
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w+", delete=False) as f:
            if initial:
                f.write(initial)
            tmppath = f.name

        extra_files = []
        try:
            editor_parts = editor.split()
            editor_bin = os.path.basename(editor_parts[0])
            cmd = list(editor_parts)
            shortcodes = self._get_emoji_names() if editor_bin in ("nvim", "vim") else []

            if editor_bin == "nvim" and shortcodes:
                with tempfile.NamedTemporaryFile(suffix=".lua", mode="w", delete=False) as lf:
                    lf.write(_build_emoji_lua(shortcodes))
                    lua_path = lf.name
                extra_files.append(lua_path)
                cmd += ["-c", f"luafile {lua_path}"]
                print("絵文字補完: 挿入モードで `:` を入力すると候補が出ます (部分一致)")
            elif editor_bin == "vim" and shortcodes:
                with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as df:
                    for name in shortcodes:
                        df.write(f":{name}:\n")
                    dict_path = df.name
                extra_files.append(dict_path)
                cmd += [
                    "-c", "set iskeyword+=58",  # 58 = ':'
                    "-c", f"set dictionary={dict_path}",
                    "-c", "set complete+=k",
                ]
                print("絵文字補完: <C-n> / <C-p> または <C-x><C-k>")

            # If initial text was provided, jump cursor to end and start insert mode
            if initial and editor_bin in ("nvim", "vim"):
                cmd += ["-c", "normal! G$", "-c", "startinsert!"]

            cmd.append(tmppath)
            subprocess.call(cmd)
            with open(tmppath) as f:
                text = f.read().strip()
            return text or None
        finally:
            os.unlink(tmppath)
            for p in extra_files:
                if os.path.exists(p):
                    os.unlink(p)

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
            self.user_id = user.get("id")
            self._emoji_cache = None
            self._note_meta = []
            print(f"ログイン成功: {name}")
        except Exception as e:
            print(f"ログイン失敗: {e}")

    def _reload_client(self):
        self.client = MisskeyClient()
        self.username = None
        self.user_id = None
        self._emoji_cache = None
        self._note_meta = []
        if self.client.logged_in:
            try:
                me = self.client.i()
                self.username = me["username"]
                self.user_id = me["id"]
            except Exception:
                print("保存済みトークンが無効です。")
                self.client.token = None

    def cmd_account(self, arg):
        parts = arg.strip().split()
        if not parts:
            accounts = config.list_accounts()
            if not accounts:
                print("アカウントがありません。'login <host>' でログインしてください。")
                return
            for a in accounts:
                mark = "*" if a["active"] else " "
                uname = f"@{a['username']}" if a["username"] else "(unknown)"
                print(f"  {mark} {uname}@{a['host']}")
            return
        sub = parts[0]
        if sub == "use":
            if len(parts) < 2:
                print("使い方: account use @user@host  (1ホスト1アカウントなら host のみでも可)")
                return
            target = parts[1]
            result = config.switch_account(target)
            if result == "not_found":
                print(f"アカウントが見つかりません: {target}")
                return
            if result == "ambiguous":
                print(f"複数該当します。'@user@host' で指定してください: {target}")
                return
            self._reload_client()
            who = f"@{self.username}@{self.client.host}" if self.username else target
            print(f"切替: {who}")
        else:
            print(f"不明なサブコマンド: {sub}")

    def cmd_logout(self, arg):
        if not self.client.logged_in:
            print("ログインしていません。")
            return
        host = self.client.host
        config.delete_active_account()
        self._reload_client()
        print(f"ログアウト: {host}")

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
        tl_type = parts[0] if parts else config.get_default_timeline()
        limit = int(parts[1]) if len(parts) > 1 else 10
        try:
            notes = self.client.timeline(tl_type, limit)
            if not notes:
                print("ノートがありません。")
                return
            self._collect_notes(notes)
            for note in reversed(notes):
                print_formatted_text(FormattedText(_format_note(note)))
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

    def cmd_default_timeline(self, arg):
        v = arg.strip()
        if not v:
            print(f"現在のデフォルト: {config.get_default_timeline()}")
            return
        if v not in TL_TYPES:
            print(f"不正な値です。選択肢: {', '.join(TL_TYPES)}")
            return
        config.set_default_timeline(v)
        print(f"デフォルトタイムラインを '{v}' に設定しました")

    def _do_reply(self, note_id, explicit_visibility, text):
        """Common reply logic. If text is None, opens editor with mention pre-filled."""
        try:
            original = self.client.show_note(note_id)
        except Exception as e:
            print(f"元ノート取得失敗: {e}")
            return

        orig_visibility = original.get("visibility", "public")
        if explicit_visibility:
            visibility = explicit_visibility
        else:
            visibility = _narrower_visibility(config.get_default_visibility(), orig_visibility)

        orig_user = original.get("user", {}) or {}
        orig_user_id = orig_user.get("id")
        orig_username = orig_user.get("username", "")
        orig_host = orig_user.get("host")
        is_self = (orig_user_id is not None and orig_user_id == self.user_id)

        mention = ""
        if not is_self and orig_username:
            mention = f"@{orig_username}" + (f"@{orig_host}" if orig_host else "")

        if text is None:
            initial = f"{mention} " if mention else ""
            text = self._edit_text(initial=initial)
            if not text:
                print("空のリプライは送信しません。")
                return
            final_text = text
        else:
            if mention and not text.startswith(mention):
                final_text = f"{mention} {text}"
            else:
                final_text = text

        kwargs = {"visibility": visibility, "reply_id": note_id}
        if visibility == "specified":
            visible_ids = list(original.get("visibleUserIds") or [])
            if orig_user_id and orig_user_id != self.user_id and orig_user_id not in visible_ids:
                visible_ids.append(orig_user_id)
            kwargs["visible_user_ids"] = visible_ids

        try:
            result = self.client.create_note(final_text, **kwargs)
            note = result["createdNote"]
            print(f"リプライしました [{note['id']}] ({visibility})")
        except Exception as e:
            print(f"エラー: {e}")

    def cmd_reply(self, arg):
        if not self._require_login():
            return
        parts = arg.strip().split()
        if not parts or len(parts) > 2:
            print("使い方: reply <note_id> [visibility]")
            return
        note_id = parts[0]
        explicit_vis = parts[1] if len(parts) > 1 else None
        if explicit_vis and explicit_vis not in VISIBILITIES:
            print(f"不正な visibility: {explicit_vis}")
            return
        self._do_reply(note_id, explicit_vis, text=None)

    def cmd_reply_text(self, arg):
        if not self._require_login():
            return
        parts = arg.strip().split(None, 2)
        if len(parts) < 2:
            print("使い方: reply_text <note_id> [visibility] <text>")
            return
        note_id = parts[0]
        if parts[1] in VISIBILITIES:
            if len(parts) < 3:
                print("使い方: reply_text <note_id> [visibility] <text>")
                return
            explicit_vis = parts[1]
            text = parts[2]
        else:
            explicit_vis = None
            text = arg.strip().split(None, 1)[1]
        self._do_reply(note_id, explicit_vis, text=text)

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
        if not reaction.startswith(":"):
            reaction = f":{reaction}:"
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
            notif_notes = [n["note"] for n in notifs if n.get("note", {}).get("id")]
            if notif_notes:
                self._collect_notes(notif_notes)
            for n in notifs:
                print_formatted_text(FormattedText(_format_notification(n)))
        except Exception as e:
            print(f"エラー: {e}")

    def cmdloop(self):
        print("Misskey CLI - 'help' でコマンド一覧、'quit' で終了")
        dispatch = {
            "login": self.cmd_login,
            "account": self.cmd_account,
            "logout": self.cmd_logout,
            "i": self.cmd_i,
            "tl": self.cmd_tl,
            "note": self.cmd_note,
            "note_text": self.cmd_note_text,
            "default_visibility": self.cmd_default_visibility,
            "default_timeline": self.cmd_default_timeline,
            "reply": self.cmd_reply,
            "reply_text": self.cmd_reply_text,
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
            except KeyboardInterrupt:
                print()
                continue
            except EOFError:
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
