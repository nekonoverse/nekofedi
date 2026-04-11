"""English catalog (source of truth).

This catalog is the canonical key set. ja.py and fr.py must export the
exact same keys (enforced by tests/test_i18n.py).
"""

CATALOG = {
    # ----- App lifecycle -----
    "app.banner": "Misskey CLI - type 'help' for commands, 'quit' to exit",
    "app.bye": "bye",

    # ----- Command help (description only; the syntax line is implicit) -----
    "cmd.help.login": "Log in to an instance",
    "cmd.help.account": "List / switch accounts",
    "cmd.help.logout": "Delete the active account",
    "cmd.help.i": "Show your profile",
    "cmd.help.tl": "Show a timeline",
    "cmd.help.note": "Compose a note in your editor",
    "cmd.help.note_text": "Post a note from the command line",
    "cmd.help.default_visibility": "Show / set the default note visibility",
    "cmd.help.default_timeline": "Show / set the default timeline",
    "cmd.help.reply": "Compose a reply in your editor",
    "cmd.help.reply_text": "Reply from the command line",
    "cmd.help.renote": "Renote a note",
    "cmd.help.react": "React to a note",
    "cmd.help.notif": "List notifications",
    "cmd.help.list": "Show lists / select active list",
    "cmd.help.lang": "Show / change display language",
    "cmd.help.help": "Show this command list",
    "cmd.help.quit": "Exit",

    # ----- Usage hints -----
    "usage.login": "Usage: login <host>  e.g. login misskey.caligula-sea.net",
    "usage.note_text": "Usage: note_text [visibility] <text>",
    "usage.account_use": "Usage: account use @user@host  (host alone works if there's only one account per host)",
    "usage.reply": "Usage: reply <note_id> [visibility]",
    "usage.reply_text": "Usage: reply_text <note_id> [visibility] <text>",
    "usage.renote": "Usage: renote <note_id>",
    "usage.react": "Usage: react <note_id> <emoji>",
    "usage.list_use": "Usage: list use <name_or_id>",

    # ----- Status / confirmation -----
    "status.login_active_as": "Logged in as {display_name}",
    "status.detected": "Detected: {software}",
    "status.login_success": "Login successful: {display_name}",
    "status.switched": "Switched to: {who}",
    "status.logout": "Logged out: {host}",
    "status.profile_counts": "  notes: {notes}  following: {following}  followers: {followers}",
    "status.posted": "Posted [{id}] ({visibility})",
    "status.replied": "Replied [{id}] ({visibility})",
    "status.renoted": "Renoted",
    "status.reacted": "Reacted {reaction}",
    "status.reacted_favourite_fallback": "Favourited (custom emoji reactions are not supported on {software})",
    "status.default_visibility_current": "Current default: {value}",
    "status.default_visibility_set": "Default visibility set to '{value}'",
    "status.default_timeline_current": "Current default: {value}",
    "status.default_timeline_set": "Default timeline set to '{value}'",
    "status.list_active_set": "Active list: {name} [{id}]",
    "status.list_active_none": "No active list. Run 'list use <name>' first.",
    "status.lang_current": "Current language: {code}  (available: {codes})",
    "status.lang_set": "Language set to '{code}'",

    # ----- Errors -----
    "error.generic": "Error: {message}",
    "error.not_logged_in": "Run 'login <host>' first.",
    "error.not_logged_in_short": "Not logged in.",
    "error.token_invalid_relogin": "Saved token is invalid. Run 'login' to re-authenticate.",
    "error.token_invalid": "Saved token is invalid.",
    "error.detect_failed": "Could not retrieve server information: {host}",
    "error.detect_failed_hint": "(nodeinfo is not reachable; please check the host name)",
    "error.unsupported_server": "This server is not supported ({software}). Only MiAuth (Misskey-family) and Mastodon-compatible servers are supported.",
    "error.user_info_failed": "Failed to retrieve user information",
    "error.login_failed": "Login failed: {message}",
    "error.account_not_found": "Account not found: {target}",
    "error.account_ambiguous": "Multiple matches. Specify '@user@host': {target}",
    "error.unknown_subcommand": "Unknown subcommand: {sub}",
    "error.invalid_choice": "Invalid value. Choices: {choices}",
    "error.fetch_parent_failed": "Failed to fetch the parent note: {message}",
    "error.invalid_visibility": "Invalid visibility: {value}",
    "error.unknown_command": "Unknown command: {cmd} (type 'help' for the list)",
    "error.unknown_timeline": "Unknown timeline: {tl_type}",
    "error.list_id_required": "list_id is required for tl_type='list'",
    "error.no_active_list": "No active list. Run 'list use <name_or_id>' to select one.",
    "error.list_not_found": "List not found: {target}",
    "error.list_ambiguous": "Multiple lists match '{target}'. Use the id.",
    "error.default_timeline_list_requires_active": "Set an active list first ('list use <name_or_id>') before setting default_timeline to 'list'.",
    "error.unknown_lang": "Unknown language: {code}  (available: {codes})",

    # ----- Empty results -----
    "empty.timeline": "No notes.",
    "empty.note": "Empty notes are not posted.",
    "empty.reply": "Empty replies are not sent.",
    "empty.notifications": "No notifications.",
    "empty.accounts": "No accounts. Run 'login <host>' to log in.",
    "empty.lists": "No lists on this server.",

    # ----- Editor hints -----
    "editor.emoji_hint_nvim": "Emoji completion: type ':' in insert mode for suggestions (substring match)",
    "editor.emoji_hint_vim": "Emoji completion: <C-n> / <C-p> or <C-x><C-k>",

    # ----- Auth (api.py) -----
    "auth.open_browser": "Open the following URL in your browser to authenticate:\n{url}",
    "auth.press_enter": "\nPress Enter once authentication is complete...",
    "auth.miauth_failed": "Authentication failed",
    "auth.paste_code": "\nPaste the authorization code and press Enter: ",
    "auth.code_missing": "No authorization code was entered",

    # ----- Meta -----
    "meta.account_active": "(active)",
}
