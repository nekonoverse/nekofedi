# nekofedi

prompt_toolkit ベースの fediverse インタラクティブ CLI クライアント。Misskey / Mastodon / Fedibird / Pleroma / Akkoma / GoToSocial / Hometown / Nekonoverse 等、絵文字リアクションが使える幅広いサーバに対応。

## セットアップ

```sh
docker pull ghcr.io/nekonoverse/nekofedi:latest
mkdir -p ~/.config/nekofedi
```

## 使い方

```sh
docker run -it --user $(id -u):$(id -g) \
  -e TZ=Asia/Tokyo \
  -e LANG=ja_JP.UTF-8 \
  -v ~/.config/nekofedi:/home/user/.config/nekofedi \
  ghcr.io/nekonoverse/nekofedi:latest
```

`TZ` 環境変数でタイムラインの日時表示タイムゾーンを指定できます (省略時は UTC)。
`LANG` で表示言語の OS ロケールを指定できます (デフォルトは英語、上記は日本語起動の例)。

## 対応サーバー

- **Misskey 系** (Misskey / Sharkey / Firefish / Iceshrimp / CherryPick / Foundkey / Meisskey / Catodon / Magnetar): MiAuth でログイン
- **Mastodon 系** (Mastodon / Fedibird / Pleroma / Akkoma / GoToSocial / Hometown / Nekonoverse): Mastodon 互換 OAuth (OOB) でログイン

`login <host>` 実行時に nodeinfo からサーバー種別を自動判別します。
ローカル検証用に `login http://localhost:8000` のように `http://` / `https://` プレフィックスを付けることもできます (省略時は https)。

### リストタイムライン

サーバー上で作成済みのユーザーリストを使ってタイムラインを取得できます:

1. `list` でアカウントのリスト一覧を表示
2. `list use <name_or_id>` でアクティブリストを切り替え
3. `tl list` でアクティブリストのタイムラインを表示
4. `tl list <name_or_id> [件数]` で任意のリストを一時的に指定して表示
5. `default_timeline list` でデフォルトを「アクティブリスト」に設定 (事前に `list use` 必須)
6. `default_timeline list <name_or_id>` でアクティブリスト切替 + デフォルト設定を一気に

実際に叩くエンドポイントはサーバー種別で自動切替されます:

- **Misskey 系**: `POST api/notes/user-list-timeline` (`listId` 指定)
- **Mastodon / Fedibird / Pleroma / Akkoma / GoToSocial / Hometown / Nekonoverse**: `GET api/v1/timelines/list/:list_id`

Mastodon 家系はリスト名を `title` で返しますが CLI 側で `name` に正規化されます。

### リアクションの挙動

`react` コマンドはサーバー種別に応じて自動でエンドポイントを切り替えます:

- **Misskey 系**: ネイティブの絵文字リアクション (`api/notes/reactions/create`)
- **Pleroma / Akkoma**: Pleroma 拡張 (`PUT /api/v1/pleroma/statuses/:id/reactions/:emoji`) でカスタム絵文字を含めてリアクション可能
- **Fedibird**: Fedibird 独自の絵文字リアクション API (`PUT /api/v1/statuses/:id/emoji_reactions/:emoji`)
- **Nekonoverse**: Mastodon 互換のリアクション API (`POST /api/v1/statuses/:id/react/:emoji`)
- **Mastodon / GoToSocial / Hometown**: 絵文字リアクション API が存在しないため、`favourite` (お気に入り) にフォールバックします (カスタム絵文字も一律 ⭐ 相当)

## コマンド一覧

| コマンド | 説明 |
|---------|------|
| `login <host>` | インスタンスにログイン (Misskey 系は MiAuth、Nekonoverse は OAuth OOB を自動選択) |
| `account` | 登録済みアカウント一覧 (アクティブに `*`) |
| `account use @user@host` | アクティブアカウントを切り替え (1ホスト1アカウントなら host のみでも可) |
| `logout` | アクティブアカウントを削除 |
| `i` | 自分のプロフィール表示 |
| `tl [home\|local\|hybrid\|global\|list] [件数]` | タイムライン表示 (`list` 時は `list use` で選択中のアクティブリスト)。件数省略時は `count` の既定値 |
| `tl list <name_or_id> [件数]` | 任意のリストタイムラインを一時指定で表示 (アクティブリストは変更されない) |
| `more` / `next` | 直近に表示したタイムラインの続き (より古いノート) を読み込む |
| `count [n]` | タイムラインの既定取得件数の確認 / 設定 (グローバル設定) |
| `note [visibility]` | エディタ ($EDITOR, デフォルト nvim) でノートを書いて投稿 |
| `note_text [visibility] <text>` | テキスト直接指定で投稿 |
| `reply <note_id> [visibility]` | エディタでリプライ作成 (メンション自動付与) |
| `reply_text <note_id> [visibility] <text>` | テキスト直接指定でリプライ |
| `renote <note_id>` | リノート |
| `react <note_id> <emoji>` | リアクション (コロン不要、自動付与) |
| `preview <note_id> [画像番号]` | 添付画像をターミナルに表示 (番号省略で全画像) |
| `image_backend [auto\|sixel\|kitty\|256]` | 画像表示バックエンドの確認 / 設定 (グローバル設定) |
| `notif [件数]` | 通知一覧 |
| `default_visibility [visibility]` | デフォルト公開範囲の設定/確認 (アクティブアカウントごと) |
| `default_timeline [home\|local\|hybrid\|global\|list]` | デフォルトタイムラインの設定/確認 (アクティブアカウントごと) |
| `default_timeline list <name_or_id>` | アクティブリスト切替 + デフォルトを `list` に設定 |
| `list` | リスト一覧を表示 (アクティブなリストに `*`) |
| `list use <name_or_id>` | アクティブリストを切り替え (`tl list` / `default_timeline list` で使用) |
| `lang [en\|ja\|fr]` | 表示言語の確認 / 変更 (グローバル設定) |
| `help` | コマンド一覧を表示 |
| `quit` / `exit` | 終了 (C-d でも終了) |

visibility: `public` / `home` / `followers` / `specified`

### Mastodon 風エイリアス

Mastodon ユーザー向けに、Misskey 用語のコマンドに Mastodon 風のエイリアスを用意しています。エイリアスは補完 / `help` の両方に表示され、Tab 補完もキャノニカルコマンドと同じ引数候補を出します。

| エイリアス | 対応するコマンド |
|------------|------------------|
| `post` | `note` |
| `post_text` | `note_text` |
| `toot` | `note` |
| `toot_text` | `note_text` |
| `boost` | `renote` |
| `whoami` | `i` |
| `next` | `more` |

例: `toot_text public Hello!` は `note_text public Hello!` と等価です。

リプライ時:
- visibility 省略時は **`default_visibility` と元ノートの visibility のうち狭い方** を採用します (元より広げず、自分の好みより広げず)
- 元投稿者へのメンション (`@user[@host]`) は自動で先頭に付与されます (自分自身へのリプライ時はスキップ)
- 元ノートが `specified` の場合、元の `visibleUserIds` と元投稿者を引き継ぎます

## 補完

Tab キーでドロップダウン補完が表示されます。

- コマンド名
- `tl` / `default_timeline` のタイムライン種別
- `tl list <name>` / `default_timeline list <name>` のリスト名 (アクティブリストに `*` マーク)
- `note` / `note_text` / `default_visibility` の公開範囲
- `reply` / `renote` / `react` のノートID (直近の tl/notif から取得、新しい順)
- `preview` のノートID は **画像添付があるノートのみ** に絞られ、添付枚数 (`📎n`) が候補に表示されます
- `react` の絵文字ショートコード (部分一致検索)
- `account use` のアカウント (`@user@host`、登録済みから)
- `list use` のリスト名 (ログイン中アカウントのリストから)

`note` でエディタが nvim の場合、挿入モードで `:` を入力するとポップアップが出て、続けてタイプすると部分一致で絞り込まれます (Misskey Web UI 風)。`<C-n>`/`<C-p>` で選択、`<C-y>` で確定。
vim の場合は dictionary completion として読み込まれるので、`<C-n>` または `<C-x><C-k>` で `:emoji_name:` を補完できます。

## 画像プレビュー

`preview <note_id>` で添付画像をターミナルに直接表示します。画像番号を省略すると **そのノートの全画像** を順に表示し、`preview <note_id> 2` のように指定すると 2 枚目だけを表示します (複数枚あるときは `[n/総数]` の見出し付き)。

バックエンドは `image_backend` で選択できます:

- `auto` (既定) — 端末を判定して `kitty` → `sixel` → `256` の順に選択
- `kitty` — Kitty graphics protocol (kitty, Ghostty, 新しめの WezTerm)
- `sixel` — sixel 対応端末 (foot, WezTerm, mlterm, Konsole, iTerm2, xterm 等)
- `256` — xterm 256 色ハーフブロック (どこでも動く最終手段)

### tmux / screen での Kitty 表示

tmux や screen の中では端末グラフィックスのエスケープが多重化レイヤーに飲み込まれるため、そのままでは Kitty 画像が表示されません。nekofedi は tmux/screen を検出すると DCS passthrough でエスケープを包んで外側の端末へ転送します。これを有効にするには **tmux 側で passthrough を許可**してください (tmux 3.3 以降):

```tmux
set -g allow-passthrough on
```

## プロンプト

```
@username@instance.host [public]>
```

ログイン前は `(no login) [public]>` と表示されます。C-c で入力中の行をキャンセルできます。

## 非対話実行 (スクリプト)

対話プロンプト以外に、コマンド列をスクリプトとして流し込めます:

```sh
# -c で 1 行ずつ (繰り返し指定可)
nekofedi -c "account use @alice@misskey.example" -c "note_text public Hello"

# -f でファイルから (`-` は stdin)
nekofedi -f ./deploy.msk

# 標準入力が TTY でなければ自動的にスクリプトモード
echo "tl home 5" | nekofedi
cat deploy.msk | nekofedi
```

スクリプト形式:

- 1 行 1 コマンド (対話モードと同じ構文)
- 空行は無視
- `#` で始まる行はコメント
- `quit` / `exit` で途中終了 (成功扱い)
- 1 つでもコマンドが失敗すると終了コード 1、全部成功で 0
- エラーメッセージは stderr に出るので `2>` でリダイレクト可

Docker からは標準入力をつないで実行:

```sh
docker run --rm -i --user $(id -u):$(id -g) \
  -v ~/.config/nekofedi:/home/user/.config/nekofedi \
  ghcr.io/nekonoverse/nekofedi:latest -c "tl home 5"
```

`note` / `reply` / `login` (MiAuth) はエディタやブラウザを開くためスクリプト向きではありません。事前に対話モードでログインしておき、スクリプトでは `note_text` / `reply_text` を使ってください。

## 設定

`~/.config/nekofedi/` に SQLite データベースとコマンド履歴が保存されます。
スキーマ変更は Alembic マイグレーションで管理されており、起動時に自動適用されます。
トークンは初回ログイン後に永続化され、次回以降は自動ログインします。

表示言語は `lang` コマンドで切り替え可能 (en / ja / fr、デフォルトは en)。
起動時の決定順序: `NEKOFEDI_LANG` → DB 保存値 → `LANG` の先頭2文字 → en
Docker イメージには `en_US.UTF-8` / `ja_JP.UTF-8` / `fr_FR.UTF-8` ロケールが入っているので、`-e LANG=ja_JP.UTF-8` 等で OS ロケールごと切替できます。

## ライセンス

[MIT](LICENSE)
