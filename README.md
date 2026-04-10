# misskey-cli

prompt_toolkit ベースの Misskey インタラクティブ CLI クライアント。

## セットアップ

```sh
docker pull ghcr.io/nananek/misskey-cli:latest
mkdir -p ~/.config/misskey-cli
```

## 使い方

```sh
docker run -it --user $(id -u):$(id -g) \
  -e TZ=Asia/Tokyo \
  -v ~/.config/misskey-cli:/home/user/.config/misskey-cli \
  ghcr.io/nananek/misskey-cli:latest
```

`TZ` 環境変数でタイムラインの日時表示タイムゾーンを指定できます (省略時は UTC)。

## 対応サーバー

- **Misskey 系** (Misskey / Sharkey / Firefish / Iceshrimp / CherryPick / Foundkey / Meisskey / Catodon / Magnetar): MiAuth でログイン
- **Nekonoverse**: Mastodon 互換 OAuth (OOB) でログイン

`login <host>` 実行時に nodeinfo からサーバー種別を自動判別します。
ローカル検証用に `login http://localhost:8000` のように `http://` / `https://` プレフィックスを付けることもできます (省略時は https)。

## コマンド一覧

| コマンド | 説明 |
|---------|------|
| `login <host>` | インスタンスにログイン (Misskey 系は MiAuth、Nekonoverse は OAuth OOB を自動選択) |
| `account` | 登録済みアカウント一覧 (アクティブに `*`) |
| `account use @user@host` | アクティブアカウントを切り替え (1ホスト1アカウントなら host のみでも可) |
| `logout` | アクティブアカウントを削除 |
| `i` | 自分のプロフィール表示 |
| `tl [home\|local\|hybrid\|global] [件数]` | タイムライン表示 |
| `note [visibility]` | エディタ ($EDITOR, デフォルト nvim) でノートを書いて投稿 |
| `note_text [visibility] <text>` | テキスト直接指定で投稿 |
| `reply <note_id> [visibility]` | エディタでリプライ作成 (メンション自動付与) |
| `reply_text <note_id> [visibility] <text>` | テキスト直接指定でリプライ |
| `renote <note_id>` | リノート |
| `react <note_id> <emoji>` | リアクション (コロン不要、自動付与) |
| `notif [件数]` | 通知一覧 |
| `default_visibility [visibility]` | デフォルト公開範囲の設定/確認 (アクティブアカウントごと) |
| `default_timeline [home\|local\|hybrid\|global]` | デフォルトタイムラインの設定/確認 (アクティブアカウントごと) |
| `help` | コマンド一覧を表示 |
| `quit` / `exit` | 終了 (C-d でも終了) |

visibility: `public` / `home` / `followers` / `specified`

リプライ時:
- visibility 省略時は **`default_visibility` と元ノートの visibility のうち狭い方** を採用します (元より広げず、自分の好みより広げず)
- 元投稿者へのメンション (`@user[@host]`) は自動で先頭に付与されます (自分自身へのリプライ時はスキップ)
- 元ノートが `specified` の場合、元の `visibleUserIds` と元投稿者を引き継ぎます

## 補完

Tab キーでドロップダウン補完が表示されます。

- コマンド名
- `tl` / `default_timeline` のタイムライン種別
- `note` / `note_text` / `default_visibility` の公開範囲
- `reply` / `renote` / `react` のノートID (直近の tl/notif から取得、新しい順)
- `react` の絵文字ショートコード (部分一致検索)
- `account use` のアカウント (`@user@host`、登録済みから)

`note` でエディタが nvim の場合、挿入モードで `:` を入力するとポップアップが出て、続けてタイプすると部分一致で絞り込まれます (Misskey Web UI 風)。`<C-n>`/`<C-p>` で選択、`<C-y>` で確定。
vim の場合は dictionary completion として読み込まれるので、`<C-n>` または `<C-x><C-k>` で `:emoji_name:` を補完できます。

## プロンプト

```
@username@instance.host [public]>
```

ログイン前は `(no login) [public]>` と表示されます。C-c で入力中の行をキャンセルできます。

## 設定

`~/.config/misskey-cli/` に SQLite データベースとコマンド履歴が保存されます。
スキーマ変更は Alembic マイグレーションで管理されており、起動時に自動適用されます。
トークンは初回ログイン後に永続化され、次回以降は自動ログインします。

## ライセンス

[MIT](LICENSE)
