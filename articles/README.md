# ブログ記事の自動アップロード

`articles/` に置いた HTML 記事を、**WordPress に自動でアップロード（新規作成 / 更新）** する仕組みです。
`main`（または開発ブランチ）に push すると、GitHub Actions が変更された記事だけを WordPress へ投稿します。

## 記事の書き方

1. `articles/` に `.html` ファイルを作成します（ファイル名がそのまま slug になります）。
2. ファイル先頭の HTML コメントにメタ情報を書きます。本文は HTML で直接記述します。

```html
<!-- wp
title: 記事タイトル              # 必須
slug: my-article               # 省略時はファイル名（例: my-article.html → my-article）
status: draft                  # draft / publish / pending / private（省略時は draft）
categories: FX入門, 注文方法     # カンマ区切り。存在しなければ自動作成
tags: USDJPY, 指値
excerpt: 抜粋（一覧に出る説明文）
-->
<h2>見出し</h2>
<p>本文をHTMLで書きます。</p>
```

- **更新の仕組み**: `slug` で WordPress 上の既存投稿を照合します。同じ slug の記事を再 push すると、新規作成ではなく**更新**されます（重複しません）。
- **公開ステータス**: 既定は `draft`（下書き）です。WordPress 管理画面で確認してから手動で公開してください。記事ごとに `status: publish` で上書きできます。
- サンプル: `sample-usdjpy-limit-order.html`

## 初期セットアップ（一度だけ）

### 1. WordPress でアプリケーションパスワードを発行

1. WordPress 管理画面 → **ユーザー → プロフィール**
2. 下部の **「アプリケーションパスワード」** で名前（例: `github-actions`）を入力して発行
3. 表示されたパスワード（スペース込み）を控える
   - ※ アプリケーションパスワードが表示されない場合は、サイトが HTTPS であること、`Application Passwords` が有効であることを確認してください。

### 2. GitHub Secrets を登録

リポジトリの **Settings → Secrets and variables → Actions → New repository secret** で以下を登録します。

| Secret 名         | 値                                            |
| ----------------- | --------------------------------------------- |
| `WP_URL`          | サイトURL（例: `https://example.com`、末尾スラッシュ不要） |
| `WP_USER`         | WordPress のユーザー名                          |
| `WP_APP_PASSWORD` | 発行したアプリケーションパスワード               |

これで準備完了です。以降は記事を push するだけで自動アップロードされます。

## 手動アップロード（ローカル実行）

GitHub Actions を使わず、手元から実行することもできます。

```bash
export WP_URL="https://example.com"
export WP_USER="your-user"
export WP_APP_PASSWORD="xxxx xxxx xxxx xxxx"

# articles/ 内のすべての記事をアップロード
python scripts/upload_to_wordpress.py

# 特定の記事だけ
python scripts/upload_to_wordpress.py articles/my-article.html

# 送信せず内容だけ確認（認証情報不要）
python scripts/upload_to_wordpress.py --dry-run
```

## 全記事を再アップロードしたいとき

GitHub の **Actions → Upload articles to WordPress → Run workflow** で
`all` を `true` にして実行すると、`articles/` 内のすべての記事を再アップロード（更新）します。
