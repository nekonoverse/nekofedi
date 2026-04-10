# misskey-cli

Python `cmd` ベースの Misskey インタラクティブ CLI クライアント。

## セットアップ

```sh
docker pull ghcr.io/nananek/misskey-cli:latest
mkdir -p ~/.config/misskey-cli
```

## 使い方

```sh
docker run -it --user $(id -u):$(id -g) \
  -v ~/.config/misskey-cli:/home/user/.config/misskey-cli \
  ghcr.io/nananek/misskey-cli:latest
```

## コマンド一覧

| コマンド | 説明 |
|---------|------|
| `login <host>` | インスタンスにログイン (MiAuth) |
| `i` | 自分のプロフィール表示 |
| `tl [home\|local\|hybrid\|global] [件数]` | タイムライン表示 |
| `note [visibility]` | nvim でノートを書いて投稿 |
| `note_text [visibility] <text>` | テキスト直接指定で投稿 |
| `reply <note_id> <text>` | リプライ |
| `renote <note_id>` | リノート |
| `react <note_id> <emoji>` | リアクション |
| `notif [件数]` | 通知一覧 |
| `default_visibility [visibility]` | デフォルト公開範囲の設定/確認 |
| `quit` | 終了 |

visibility: `public` / `home` / `followers` / `specified`

## プロンプト

```
@username@instance.host [public]>
```

ログイン前は `(no login) [public]>` と表示されます。

## 設定

`~/.config/misskey-cli/` に SQLite データベースと readline 履歴が保存されます。
トークンは初回ログイン後に永続化され、次回以降は自動ログインします。

## ライセンス

[MIT](LICENSE)
