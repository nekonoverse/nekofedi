"""Japanese catalog. Mirrors the key set of en.py exactly."""

CATALOG = {
    # ----- App lifecycle -----
    "app.banner": "Misskey CLI - 'help' でコマンド一覧、'quit' で終了",
    "app.bye": "bye",

    # ----- Command help (description only; the syntax line is implicit) -----
    "cmd.help.login": "インスタンスにログイン",
    "cmd.help.account": "アカウント一覧 / 切替",
    "cmd.help.logout": "アクティブなアカウントを削除",
    "cmd.help.i": "自分のプロフィール表示",
    "cmd.help.tl": "タイムライン表示",
    "cmd.help.note": "エディタでノート作成",
    "cmd.help.note_text": "テキスト直接指定でノート投稿",
    "cmd.help.default_visibility": "デフォルト公開範囲の確認 / 設定",
    "cmd.help.default_timeline": "デフォルトタイムラインの確認 / 設定",
    "cmd.help.reply": "エディタでリプライ作成",
    "cmd.help.reply_text": "テキスト直接指定でリプライ",
    "cmd.help.renote": "リノート",
    "cmd.help.react": "リアクション",
    "cmd.help.notif": "通知一覧",
    "cmd.help.list": "リスト一覧表示 / アクティブリスト切替",
    "cmd.help.lang": "表示言語の確認 / 変更",
    "cmd.help.help": "コマンド一覧を表示",
    "cmd.help.quit": "終了",

    # ----- Usage hints -----
    "usage.login": "使い方: login <host>  例: login misskey.caligula-sea.net",
    "usage.note_text": "使い方: note_text [visibility] <text>",
    "usage.account_use": "使い方: account use @user@host  (1ホスト1アカウントなら host のみでも可)",
    "usage.reply": "使い方: reply <note_id> [visibility]",
    "usage.reply_text": "使い方: reply_text <note_id> [visibility] <text>",
    "usage.renote": "使い方: renote <note_id>",
    "usage.react": "使い方: react <note_id> <emoji>",
    "usage.list_use": "使い方: list use <name_or_id>",

    # ----- Status / confirmation -----
    "status.login_active_as": "{display_name} としてログイン中",
    "status.detected": "検出: {software}",
    "status.login_success": "ログイン成功: {display_name}",
    "status.switched": "切替: {who}",
    "status.logout": "ログアウト: {host}",
    "status.profile_counts": "  ノート数: {notes}  フォロー: {following}  フォロワー: {followers}",
    "status.posted": "投稿しました [{id}] ({visibility})",
    "status.replied": "リプライしました [{id}] ({visibility})",
    "status.renoted": "リノートしました",
    "status.reacted": "リアクションしました {reaction}",
    "status.reacted_favourite_fallback": "お気に入りに追加しました (カスタム絵文字リアクションは {software} では使えません)",
    "status.default_visibility_current": "現在のデフォルト: {value}",
    "status.default_visibility_set": "デフォルト公開範囲を '{value}' に設定しました",
    "status.default_timeline_current": "現在のデフォルト: {value}",
    "status.default_timeline_set": "デフォルトタイムラインを '{value}' に設定しました",
    "status.list_active_set": "アクティブリスト: {name} [{id}]",
    "status.list_active_none": "アクティブリスト未設定。'list use <name>' で選択してください。",
    "status.lang_current": "現在の言語: {code}  (選択肢: {codes})",
    "status.lang_set": "言語を '{code}' に設定しました",

    # ----- Errors -----
    "error.generic": "エラー: {message}",
    "error.not_logged_in": "先に 'login <host>' でログインしてください。",
    "error.not_logged_in_short": "ログインしていません。",
    "error.token_invalid_relogin": "保存済みトークンが無効です。'login' で再認証してください。",
    "error.token_invalid": "保存済みトークンが無効です。",
    "error.detect_failed": "サーバー情報を取得できませんでした: {host}",
    "error.detect_failed_hint": "(nodeinfo にアクセスできません。ホスト名を確認してください)",
    "error.unsupported_server": "このサーバーは未対応です ({software})。MiAuth 対応 (Misskey 系) と Mastodon 互換サーバーのみサポートしています。",
    "error.user_info_failed": "ユーザー情報の取得に失敗しました",
    "error.login_failed": "ログイン失敗: {message}",
    "error.account_not_found": "アカウントが見つかりません: {target}",
    "error.account_ambiguous": "複数該当します。'@user@host' で指定してください: {target}",
    "error.unknown_subcommand": "不明なサブコマンド: {sub}",
    "error.invalid_choice": "不正な値です。選択肢: {choices}",
    "error.fetch_parent_failed": "元ノート取得失敗: {message}",
    "error.invalid_visibility": "不正な visibility: {value}",
    "error.unknown_command": "不明なコマンド: {cmd} ('help' で一覧表示)",
    "error.unknown_timeline": "不明なタイムライン: {tl_type}",
    "error.list_id_required": "tl_type='list' には list_id が必要です",
    "error.no_active_list": "アクティブリスト未設定。'list use <name_or_id>' で選択してください。",
    "error.list_not_found": "リストが見つかりません: {target}",
    "error.list_ambiguous": "'{target}' に複数該当します。ID で指定してください。",
    "error.default_timeline_list_requires_active": "先に 'list use <name_or_id>' でアクティブリストを選択してから default_timeline を 'list' に設定してください。",
    "error.unknown_lang": "不明な言語: {code}  (選択肢: {codes})",

    # ----- Empty results -----
    "empty.timeline": "ノートがありません。",
    "empty.note": "空のノートは投稿しません。",
    "empty.reply": "空のリプライは送信しません。",
    "empty.notifications": "通知はありません。",
    "empty.accounts": "アカウントがありません。'login <host>' でログインしてください。",
    "empty.lists": "このサーバーにリストがありません。",

    # ----- Editor hints -----
    "editor.emoji_hint_nvim": "絵文字補完: 挿入モードで `:` を入力すると候補が出ます (部分一致)",
    "editor.emoji_hint_vim": "絵文字補完: <C-n> / <C-p> または <C-x><C-k>",

    # ----- Auth (api.py) -----
    "auth.open_browser": "ブラウザで以下のURLを開いて認証してください:\n{url}",
    "auth.press_enter": "\n認証が完了したらEnterを押してください...",
    "auth.miauth_failed": "認証に失敗しました",
    "auth.paste_code": "\n認可コードを貼り付けて Enter: ",
    "auth.code_missing": "認可コードが入力されませんでした",

    # ----- Meta -----
    "meta.account_active": "(アクティブ)",
}
