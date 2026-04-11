import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime

from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory

from .api import (
    MASTODON_SOFTWARE,
    MIAUTH_SOFTWARE,
    detect_software,
    make_client,
    parse_host_arg,
)
from . import config, i18n
from .i18n import _

HISTORY_FILE = str(config.CONFIG_DIR / "history")

VISIBILITIES = ("public", "home", "followers", "specified")
# Wider to narrower
VISIBILITY_RANK = {"public": 0, "home": 1, "followers": 2, "specified": 3}


def _narrower_visibility(a, b):
    return a if VISIBILITY_RANK.get(a, 0) >= VISIBILITY_RANK.get(b, 0) else b
TL_TYPES = ("home", "local", "hybrid", "global", "list")

# Supported terminal image backends for the `preview` command.
IMAGE_BACKENDS = ("auto", "sixel", "kitty", "256")

# Commands that terminate a cmdloop / script run instead of dispatching.
QUIT_COMMANDS = ("quit", "exit")

# Mastodon-style aliases → canonical (Misskey-style) command name.
# Resolved in ``_dispatch_line`` before dispatch and normalised in
# :class:`MisskeyCompleter` before arg-position checks, so aliases get the
# same completion behaviour as their canonical counterparts.
ALIASES = {
    "post": "note",
    "post_text": "note_text",
    "toot": "note",
    "toot_text": "note_text",
    "boost": "renote",
    "whoami": "i",
}

# Map command name → catalog key holding its description.
COMMANDS = {
    "login": "cmd.help.login",
    "account": "cmd.help.account",
    "logout": "cmd.help.logout",
    "i": "cmd.help.i",
    "tl": "cmd.help.tl",
    "note": "cmd.help.note",
    "note_text": "cmd.help.note_text",
    "default_visibility": "cmd.help.default_visibility",
    "default_timeline": "cmd.help.default_timeline",
    "reply": "cmd.help.reply",
    "reply_text": "cmd.help.reply_text",
    "renote": "cmd.help.renote",
    "react": "cmd.help.react",
    "preview": "cmd.help.preview",
    "notif": "cmd.help.notif",
    "list": "cmd.help.list",
    "lang": "cmd.help.lang",
    "image_backend": "cmd.help.image_backend",
    "help": "cmd.help.help",
    "quit": "cmd.help.quit",
    "exit": "cmd.help.quit",
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

    files = note.get("files") or []
    if files:
        # 📎 [1]image [2]video NSFW [3]audio
        # English protocol-term labels (not i18n'd). The 'NSFW' suffix
        # marks per-attachment sensitivity on Misskey, and the note-level
        # sensitive flag on Mastodon.
        marker = "  \U0001f4ce"
        for i, f in enumerate(files, start=1):
            kind = f.get("type") or "file"
            nsfw = " NSFW" if f.get("sensitive") else ""
            marker += f" [{i}]{kind}{nsfw}"
        parts.append(("ansiblue", marker + "\n"))

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


NOTE_ID_COMMANDS = ("reply", "reply_text", "renote", "react", "preview")


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
    def __init__(self, get_emoji_names, get_note_meta, get_lists):
        self._get_emoji_names = get_emoji_names
        self._get_note_meta = get_note_meta
        self._get_lists = get_lists

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        parts = text.split()

        if not parts or (len(parts) == 1 and not text.endswith(" ")):
            # Completing command name (canonical commands + Mastodon-style aliases)
            word = parts[0] if parts else ""
            for cmd_name, desc_key in COMMANDS.items():
                if cmd_name.startswith(word):
                    yield Completion(cmd_name, start_position=-len(word), display_meta=_(desc_key))
            for alias, canonical in ALIASES.items():
                if alias.startswith(word):
                    yield Completion(
                        alias,
                        start_position=-len(word),
                        display_meta=_("cmd.help.alias_for", canonical=canonical),
                    )
            return

        # Normalize Mastodon-style aliases so downstream arg-position
        # checks (``cmd in NOTE_ID_COMMANDS`` etc.) behave identically.
        cmd = ALIASES.get(parts[0], parts[0])
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

        if cmd in ("tl", "default_timeline") and arg_pos == 1:
            for t in TL_TYPES:
                if t.startswith(current):
                    yield Completion(t, start_position=-len(current))

        elif (
            cmd in ("tl", "default_timeline")
            and arg_pos == 2
            and parts[1] == "list"
        ):
            yield from self._complete_list_target(current)

        elif cmd in ("note", "note_text", "default_visibility") and len(parts) <= 2:
            for v in VISIBILITIES:
                if v.startswith(current):
                    yield Completion(v, start_position=-len(current))

        elif cmd == "image_backend" and arg_pos == 1:
            for b in IMAGE_BACKENDS:
                if b.startswith(current):
                    yield Completion(b, start_position=-len(current))

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
                        meta = _("meta.account_active") if a["active"] else ""
                        yield Completion(acct, start_position=-len(current), display_meta=meta)

        elif cmd == "list":
            if arg_pos == 1:
                for sub in ("use",):
                    if sub.startswith(current):
                        yield Completion(sub, start_position=-len(current))
            elif arg_pos == 2 and len(parts) >= 2 and parts[1] == "use":
                yield from self._complete_list_target(current)

    def _complete_list_target(self, current):
        active_id = config.get_active_list_id()
        for lst in self._get_lists():
            name = lst.get("name") or ""
            if name.startswith(current):
                meta = (
                    _("meta.account_active")
                    if lst["id"] == active_id
                    else f"[{lst['id']}]"
                )
                yield Completion(
                    name, start_position=-len(current), display_meta=meta
                )


class MisskeyCLI:
    def __init__(self):
        self.username = None
        self.user_id = None
        self._emoji_cache = None
        self._lists_cache = None
        self._note_meta = []
        self._had_error = False
        self._initial_display = None
        self._dispatch = None
        self.client = make_client()
        if self.client.logged_in:
            try:
                me = self.client.i()
                self.username = me["username"]
                self.user_id = me["id"]
                self._initial_display = me.get("name") or me["username"]
            except Exception:
                # Printed directly (not via ``_error``) so ``_had_error``
                # stays False at construction time. ``run_script`` would
                # reset it anyway, but we also don't want to accidentally
                # poison a subsequent call.
                print(_("error.token_invalid_relogin"), file=sys.stderr)
                self.client.token = None

        config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        # Created lazily on first cmdloop() call so script mode
        # (``-c`` / ``-f`` / piped stdin) never touches the terminal.
        self.session = None

    def _greet_active_account(self):
        """Show the 'Logged in as X' line. Called only from ``cmdloop``
        so script-mode invocations keep stdout clean."""
        if self._initial_display:
            print(_("status.login_active_as", display_name=self._initial_display))

    def _ensure_session(self):
        if self.session is None:
            self.session = PromptSession(
                history=FileHistory(HISTORY_FILE),
                completer=MisskeyCompleter(
                    self._get_emoji_names, self._get_note_meta, self._get_lists
                ),
                # Run completions off the UI thread so a first-time
                # ``list use`` / emoji lookup doesn't block the REPL
                # on a network round-trip.
                complete_in_thread=True,
            )

    def _get_emoji_names(self):
        if self._emoji_cache is None and self.client.logged_in:
            try:
                emojis = self.client.emojis()
                self._emoji_cache = [e['name'] for e in emojis]
            except Exception:
                self._emoji_cache = []
        return self._emoji_cache or []

    def _get_lists(self):
        """Return cached ``[{id, name}]`` lists for completion.

        Swallows errors and returns ``[]`` so the completer stays quiet on
        network hiccups. Callers that need to surface errors should use
        :meth:`_refresh_lists` instead.
        """
        if self._lists_cache is None and self.client.logged_in:
            try:
                self._lists_cache = self.client.lists() or []
            except Exception:
                self._lists_cache = []
        return self._lists_cache or []

    def _refresh_lists(self):
        """Fetch lists from the server and update the completer cache.

        Raises on network/API errors so the caller can surface them.
        """
        lists = self.client.lists() or []
        self._lists_cache = lists
        return lists

    def _resolve_list(self, target):
        """Resolve a name-or-id string against the lists cache.

        Returns ``(list_dict | None, status)`` where status is one of
        ``'ok'`` / ``'not_found'`` / ``'ambiguous'``, matching the convention
        of :func:`config.switch_account`.
        """
        if not target:
            return None, "not_found"
        lists = self._get_lists()
        matches_by_name = []
        for lst in lists:
            if lst["id"] == target:
                return lst, "ok"
            if (lst.get("name") or "") == target:
                matches_by_name.append(lst)
        if len(matches_by_name) == 1:
            return matches_by_name[0], "ok"
        if len(matches_by_name) > 1:
            return None, "ambiguous"
        return None, "not_found"

    def _activate_list(self, lst):
        """Persist ``lst`` as the active list and print the status line."""
        config.set_active_list_id(lst["id"])
        print(_(
            "status.list_active_set",
            name=lst.get("name") or "(unnamed)",
            id=lst["id"],
        ))

    def _resolve_list_with_refresh(self, target):
        """Resolve a list target, refetching once on cache miss.

        Prints a user-facing error and returns ``None`` when the target cannot
        be resolved. Returns the resolved list dict on success.
        """
        lst, status = self._resolve_list(target)
        if status == "not_found":
            try:
                self._refresh_lists()
            except Exception as e:
                self._error("error.generic", message=str(e))
                return None
            lst, status = self._resolve_list(target)
        if status == "not_found":
            self._error("error.list_not_found", target=target)
            return None
        if status == "ambiguous":
            self._error("error.list_ambiguous", target=target)
            return None
        return lst

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

    def _error(self, key, **fmt):
        """Print a user-facing error to stderr and mark the session as failed.

        Non-interactive callers (``run_script``) use ``self._had_error`` to
        decide the process exit code. Interactive ``cmdloop`` ignores the
        flag but still benefits from errors going to stderr.
        """
        print(_(key, **fmt), file=sys.stderr)
        self._had_error = True

    def _require_login(self):
        if not self.client.logged_in:
            self._error("error.not_logged_in")
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
                print(_("editor.emoji_hint_nvim"))
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
                print(_("editor.emoji_hint_vim"))

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
        for name, key in COMMANDS.items():
            print(f"  {name:22s} {_(key)}")
        print()
        print(_("cmd.help.aliases_header"))
        for alias, canonical in ALIASES.items():
            print(f"  {alias:22s} {_('cmd.help.alias_for', canonical=canonical)}")

    def cmd_login(self, arg):
        if not arg.strip():
            self._error("usage.login")
            return
        host, scheme = parse_host_arg(arg)
        software = detect_software(host, scheme=scheme)
        if software is None:
            self._error("error.detect_failed", host=host)
            self._error("error.detect_failed_hint")
            return
        print(_("status.detected", software=software))
        if software not in MIAUTH_SOFTWARE and software not in MASTODON_SOFTWARE:
            self._error("error.unsupported_server", software=software)
            return
        client = make_client(software=software, scheme=scheme)
        try:
            user = client.login(host)
            username = user.get("username")
            if not username:
                raise RuntimeError(_("error.user_info_failed"))
            config.save_credentials(
                host,
                client.token,
                username=username,
                software=software,
                scheme=scheme,
            )
            self.client = client
            self.username = username
            self.user_id = user.get("id")
            self._emoji_cache = None
            self._lists_cache = None
            self._note_meta = []
            display = user.get("name") or username
            print(_("status.login_success", display_name=display))
        except Exception as e:
            self._error("error.login_failed", message=str(e))

    def _reload_client(self):
        self.client = make_client()
        self.username = None
        self.user_id = None
        self._emoji_cache = None
        self._lists_cache = None
        self._note_meta = []
        if self.client.logged_in:
            try:
                me = self.client.i()
                self.username = me["username"]
                self.user_id = me["id"]
            except Exception:
                self._error("error.token_invalid")
                self.client.token = None

    def cmd_account(self, arg):
        parts = arg.strip().split()
        if not parts:
            accounts = config.list_accounts()
            if not accounts:
                print(_("empty.accounts"))
                return
            for a in accounts:
                mark = "*" if a["active"] else " "
                uname = f"@{a['username']}" if a["username"] else "(unknown)"
                tags = []
                if a.get("software"):
                    tags.append(a["software"])
                if a.get("scheme") == "http":
                    tags.append("http")
                tag_str = f"  ({', '.join(tags)})" if tags else ""
                print(f"  {mark} {uname}@{a['host']}{tag_str}")
            return
        sub = parts[0]
        if sub == "use":
            if len(parts) < 2:
                self._error("usage.account_use")
                return
            target = parts[1]
            result = config.switch_account(target)
            if result == "not_found":
                self._error("error.account_not_found", target=target)
                return
            if result == "ambiguous":
                self._error("error.account_ambiguous", target=target)
                return
            self._reload_client()
            who = f"@{self.username}@{self.client.host}" if self.username else target
            print(_("status.switched", who=who))
        else:
            self._error("error.unknown_subcommand", sub=sub)

    def cmd_logout(self, arg):
        if not self.client.logged_in:
            self._error("error.not_logged_in_short")
            return
        host = self.client.host
        config.delete_active_account()
        self._reload_client()
        print(_("status.logout", host=host))

    def cmd_i(self, arg):
        if not self._require_login():
            return
        try:
            me = self.client.i()
            name = me.get("name") or me["username"]
            print(f"  {name} (@{me['username']})")
            if me.get("description"):
                print(f"  {me['description']}")
            print(_(
                "status.profile_counts",
                notes=me.get("notesCount", 0),
                following=me.get("followingCount", 0),
                followers=me.get("followersCount", 0),
            ))
        except Exception as e:
            self._error("error.generic", message=str(e))

    def cmd_tl(self, arg):
        if not self._require_login():
            return
        parts = arg.strip().split()
        tl_type = parts[0] if parts else config.get_default_timeline()
        kwargs = {}
        if tl_type == "list":
            # `tl list [target] [limit]` — target is a name or id. If the
            # second token is a bare number it's the limit (active list
            # is used), otherwise it's the target. Caveat: a list whose
            # name is pure digits is unreachable via this shortcut; use
            # `list use <id>` first, then `tl list`.
            target = None
            rest = parts[1:]
            if rest and not rest[0].isdigit():
                target = rest[0]
                rest = rest[1:]
            limit = int(rest[0]) if rest else 10
            if target:
                lst = self._resolve_list_with_refresh(target)
                if lst is None:
                    return
                kwargs["list_id"] = lst["id"]
            else:
                list_id = config.get_active_list_id()
                if not list_id:
                    self._error("error.no_active_list")
                    return
                kwargs["list_id"] = list_id
        else:
            limit = int(parts[1]) if len(parts) > 1 else 10
        try:
            notes = self.client.timeline(tl_type, limit, **kwargs)
            if not notes:
                print(_("empty.timeline"))
                return
            self._collect_notes(notes)
            for note in reversed(notes):
                print_formatted_text(FormattedText(_format_note(note)))
                print()
        except Exception as e:
            self._error("error.generic", message=str(e))

    def cmd_note(self, arg):
        if not self._require_login():
            return
        visibility = self._resolve_visibility(arg.strip())
        text = self._edit_text()
        if not text:
            print(_("empty.note"))
            return
        try:
            result = self.client.create_note(text, visibility=visibility)
            note = result["createdNote"]
            print(_("status.posted", id=note["id"], visibility=visibility))
        except Exception as e:
            self._error("error.generic", message=str(e))

    def cmd_note_text(self, arg):
        if not self._require_login():
            return
        parts = arg.strip().split(None, 1)
        if not parts:
            self._error("usage.note_text")
            return
        if parts[0] in VISIBILITIES:
            visibility = parts[0]
            text = parts[1] if len(parts) > 1 else ""
        else:
            visibility = config.get_default_visibility()
            text = arg.strip()
        if not text:
            self._error("usage.note_text")
            return
        try:
            result = self.client.create_note(text, visibility=visibility)
            note = result["createdNote"]
            print(_("status.posted", id=note["id"], visibility=visibility))
        except Exception as e:
            self._error("error.generic", message=str(e))

    def cmd_default_visibility(self, arg):
        v = arg.strip()
        if not v:
            print(_("status.default_visibility_current", value=config.get_default_visibility()))
            return
        if v not in VISIBILITIES:
            self._error("error.invalid_choice", choices=", ".join(VISIBILITIES))
            return
        if not self._require_login():
            return
        config.set_default_visibility(v)
        print(_("status.default_visibility_set", value=v))

    def cmd_default_timeline(self, arg):
        parts = arg.strip().split()
        if not parts:
            print(_("status.default_timeline_current", value=config.get_default_timeline()))
            return
        v = parts[0]
        if v not in TL_TYPES:
            self._error("error.invalid_choice", choices=", ".join(TL_TYPES))
            return
        if not self._require_login():
            return
        if v == "list":
            # `default_timeline list <target>` switches the active list and
            # sets the default in one shot. Without a target, an active
            # list must already be set.
            if len(parts) >= 2:
                lst = self._resolve_list_with_refresh(parts[1])
                if lst is None:
                    return
                self._activate_list(lst)
            elif not config.get_active_list_id():
                self._error("error.default_timeline_list_requires_active")
                return
        config.set_default_timeline(v)
        print(_("status.default_timeline_set", value=v))

    def cmd_list(self, arg):
        if not self._require_login():
            return
        parts = arg.strip().split()
        if not parts:
            # Show all lists with active marker. Always hit the server so the
            # user sees the authoritative state, not a stale cache.
            try:
                lists = self._refresh_lists()
            except Exception as e:
                self._error("error.generic", message=str(e))
                return
            if not lists:
                print(_("empty.lists"))
                return
            active_id = config.get_active_list_id()
            for lst in lists:
                mark = "*" if lst["id"] == active_id else " "
                name = lst.get("name") or "(unnamed)"
                print(f"  {mark} {name}  [{lst['id']}]")
            return

        sub = parts[0]
        if sub == "use":
            if len(parts) < 2:
                self._error("usage.list_use")
                return
            lst = self._resolve_list_with_refresh(parts[1])
            if lst is None:
                return
            self._activate_list(lst)
        else:
            self._error("error.unknown_subcommand", sub=sub)

    def cmd_lang(self, arg):
        code = arg.strip()
        codes = ", ".join(i18n.SUPPORTED_LANGS)
        if not code:
            print(_("status.lang_current", code=i18n.get_language(), codes=codes))
            return
        if code not in i18n.SUPPORTED_LANGS:
            self._error("error.unknown_lang", code=code, codes=codes)
            return
        i18n.set_language(code)
        print(_("status.lang_set", code=code))

    def cmd_image_backend(self, arg):
        v = arg.strip()
        choices = ", ".join(IMAGE_BACKENDS)
        if not v:
            print(_(
                "status.image_backend_current",
                value=config.get_image_backend(),
                choices=choices,
            ))
            return
        if v not in IMAGE_BACKENDS:
            self._error("error.invalid_choice", choices=choices)
            return
        config.set_image_backend(v)
        print(_("status.image_backend_set", value=v))

    def _do_reply(self, note_id, explicit_visibility, text):
        """Common reply logic. If text is None, opens editor with mention pre-filled."""
        try:
            original = self.client.show_note(note_id)
        except Exception as e:
            self._error("error.fetch_parent_failed", message=str(e))
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
                print(_("empty.reply"))
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
            print(_("status.replied", id=note["id"], visibility=visibility))
        except Exception as e:
            self._error("error.generic", message=str(e))

    def cmd_reply(self, arg):
        if not self._require_login():
            return
        parts = arg.strip().split()
        if not parts or len(parts) > 2:
            self._error("usage.reply")
            return
        note_id = parts[0]
        explicit_vis = parts[1] if len(parts) > 1 else None
        if explicit_vis and explicit_vis not in VISIBILITIES:
            self._error("error.invalid_visibility", value=explicit_vis)
            return
        self._do_reply(note_id, explicit_vis, text=None)

    def cmd_reply_text(self, arg):
        if not self._require_login():
            return
        parts = arg.strip().split(None, 2)
        if len(parts) < 2:
            self._error("usage.reply_text")
            return
        note_id = parts[0]
        if parts[1] in VISIBILITIES:
            if len(parts) < 3:
                self._error("usage.reply_text")
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
            self._error("usage.renote")
            return
        try:
            self.client.renote(note_id)
            print(_("status.renoted"))
        except Exception as e:
            self._error("error.generic", message=str(e))

    def cmd_react(self, arg):
        if not self._require_login():
            return
        parts = arg.strip().split(None, 1)
        if len(parts) < 2:
            self._error("usage.react")
            return
        note_id, reaction = parts
        if not reaction.startswith(":"):
            reaction = f":{reaction}:"
        try:
            result = self.client.react(note_id, reaction)
            if result is None and getattr(self.client, "software", None):
                print(_("status.reacted_favourite_fallback", software=self.client.software))
            else:
                print(_("status.reacted", reaction=reaction))
        except Exception as e:
            self._error("error.generic", message=str(e))

    def cmd_preview(self, arg):
        if not self._require_login():
            return
        parts = arg.strip().split()
        if not parts:
            self._error("usage.preview")
            return
        note_id = parts[0]
        if len(parts) > 1:
            try:
                index = int(parts[1])
            except ValueError:
                self._error("usage.preview")
                return
        else:
            index = 1
        if index < 1:
            self._error("usage.preview")
            return

        try:
            note = self.client.show_note(note_id)
        except Exception as e:
            self._error("error.fetch_parent_failed", message=str(e))
            return

        files = (note or {}).get("files") or []
        images = [f for f in files if f.get("type") == "image"]
        if not images:
            self._error("empty.note_images")
            return
        if index > len(images):
            self._error("error.index_out_of_range", index=index, max=len(images))
            return

        target = images[index - 1]
        url = target.get("url")
        try:
            import shutil

            from . import image as image_mod

            term_cols = shutil.get_terminal_size(fallback=(80, 24)).columns
            backend = config.get_image_backend()
            output = image_mod.render_image_from_url_auto(
                url, max_cols=max(8, term_cols - 4), backend=backend
            )
        except Exception as e:
            self._error("error.preview_failed", message=str(e))
            return

        sys.stdout.write(output)
        sys.stdout.flush()
        alt = target.get("alt")
        if alt:
            print_formatted_text(FormattedText([
                ("ansibrightblack", f"  alt: {alt}"),
            ]))

    def cmd_notif(self, arg):
        if not self._require_login():
            return
        limit = int(arg.strip()) if arg.strip() else 10
        try:
            notifs = self.client.notifications(limit)
            if not notifs:
                print(_("empty.notifications"))
                return
            notif_notes = [n["note"] for n in notifs if n.get("note", {}).get("id")]
            if notif_notes:
                self._collect_notes(notif_notes)
            for n in notifs:
                print_formatted_text(FormattedText(_format_notification(n)))
        except Exception as e:
            self._error("error.generic", message=str(e))

    def _get_dispatch(self):
        """Lazily build and cache the command-name → handler mapping.

        Derived from the module-level :data:`COMMANDS` catalog so new
        commands only need to be added in one place. ``quit`` / ``exit``
        are not dispatchable (callers handle them specially via
        :data:`QUIT_COMMANDS`).
        """
        if self._dispatch is None:
            self._dispatch = {
                name: getattr(self, f"cmd_{name}")
                for name in COMMANDS
                if name not in QUIT_COMMANDS
            }
        return self._dispatch

    def _dispatch_line(self, line):
        """Parse and dispatch a single line.

        Returns ``True`` if the line requested a halt (``quit`` / ``exit``),
        otherwise ``False``. Empty lines are a no-op. Errors are routed
        through :meth:`_error`. Exceptions raised by handlers are caught
        and reported; this is a belt-and-braces fallback since every
        ``cmd_*`` method already has its own ``try/except``.
        """
        parts = line.split(None, 1)
        if not parts:
            return False
        cmd_name = ALIASES.get(parts[0], parts[0])
        arg = parts[1] if len(parts) > 1 else ""
        if cmd_name in QUIT_COMMANDS:
            return True
        handler = self._get_dispatch().get(cmd_name)
        if handler is None:
            self._error("error.unknown_command", cmd=cmd_name)
            return False
        try:
            handler(arg)
        except Exception as e:
            self._error("error.generic", message=str(e))
        return False

    def run_script(self, lines):
        """Execute CLI commands from an iterable of lines non-interactively.

        Blank lines and lines beginning with ``#`` are skipped. ``quit`` /
        ``exit`` halt execution. Errors from individual commands are reported
        via :meth:`_error` (stderr) and cause the script to report failure,
        but subsequent lines keep running so the user sees every problem in
        one pass.

        Returns ``True`` iff every executed command succeeded.
        """
        self._had_error = False
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if self._dispatch_line(line):
                break
        return not self._had_error

    def cmdloop(self):
        print(_("app.banner"))
        self._greet_active_account()
        self._ensure_session()

        while True:
            try:
                text = self.session.prompt(self._get_prompt()).strip()
            except KeyboardInterrupt:
                print()
                continue
            except EOFError:
                print(_("app.bye"))
                break

            if not text:
                continue

            if self._dispatch_line(text):
                print(_("app.bye"))
                break
