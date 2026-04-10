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

## コマンド一覧

| コマンド | 説明 |
|---------|------|
| `login <host>` | インスタンスにログイン (MiAuth) |
| `i` | 自分のプロフィール表示 |
| `tl [home\|local\|hybrid\|global] [件数]` | タイムライン表示 |
| `note [visibility]` | エディタ ($EDITOR, デフォルト nvim) でノートを書いて投稿 |
| `note_text [visibility] <text>` | テキスト直接指定で投稿 |
| `reply <note_id> <text>` | リプライ |
| `renote <note_id>` | リノート |
| `react <note_id> <emoji>` | リアクション (コロン不要、自動付与) |
| `notif [件数]` | 通知一覧 |
| `default_visibility [visibility]` | デフォルト公開範囲の設定/確認 |
| `default_timeline [home\|local\|hybrid\|global]` | デフォルトタイムラインの設定/確認 |
| `help` | コマンド一覧を表示 |
| `quit` / `exit` | 終了 (C-d でも終了) |

visibility: `public` / `home` / `followers` / `specified`

## 補完

Tab キーでドロップダウン補完が表示されます。

- コマンド名
- `tl` / `default_timeline` のタイムライン種別
- `note` / `note_text` / `default_visibility` の公開範囲
- `reply` / `renote` / `react` のノートID (直近の tl/notif から取得、新しい順)
- `react` の絵文字ショートコード (部分一致検索)

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
