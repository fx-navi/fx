#!/usr/bin/env python3
"""WordPress に HTML 記事をアップロード（新規作成 / 更新）するスクリプト。

- 記事は articles/*.html に置く。
- 各ファイル先頭の HTML コメントにメタ情報を記述する（下記フォーマット）。
- slug（未指定ならファイル名）で既存投稿を照合し、あれば更新・なければ新規作成する。
- 依存ライブラリなし（Python 3.8+ 標準ライブラリのみ）。

メタ情報フォーマット（ファイル先頭）:

    <!-- wp
    title: 記事タイトル
    slug: usdjpy-limit-order        # 省略時はファイル名
    status: draft                   # draft / publish / pending / private（省略時は DEFAULT_STATUS）
    categories: FX入門, 注文方法     # カンマ区切り。無ければ自動作成
    tags: USDJPY, 指値
    excerpt: 抜粋テキスト
    -->
    <h2>本文...</h2>

環境変数:
    WP_URL            例: https://example.com （末尾スラッシュ不要）
    WP_USER           WordPress ユーザー名
    WP_APP_PASSWORD   アプリケーションパスワード（設定 > ユーザー > アプリケーションパスワード）
    DEFAULT_STATUS    省略時の公開ステータス（既定: draft）

使い方:
    python scripts/upload_to_wordpress.py                 # articles/ 内の全 html
    python scripts/upload_to_wordpress.py articles/a.html # 指定ファイルのみ
    python scripts/upload_to_wordpress.py --dry-run ...   # 送信せず内容だけ確認
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ARTICLES_DIR = Path(__file__).resolve().parent.parent / "articles"
VALID_STATUSES = {"draft", "publish", "pending", "private", "future"}


def fail(msg):
    print(f"::error::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"ERROR: {msg}",
          file=sys.stderr)
    sys.exit(1)


def get_config():
    url = os.environ.get("WP_URL", "").rstrip("/")
    user = os.environ.get("WP_USER", "")
    password = os.environ.get("WP_APP_PASSWORD", "")
    if not url or not user or not password:
        fail("環境変数 WP_URL / WP_USER / WP_APP_PASSWORD を設定してください。")
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return url, {"Authorization": f"Basic {token}"}


def api_request(api_base, headers, path, method="GET", params=None, body=None):
    url = f"{api_base}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    req_headers = dict(headers)
    if data is not None:
        req_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        fail(f"WordPress API エラー [{method} {path}] {e.code}: {detail}")
    except urllib.error.URLError as e:
        fail(f"WordPress への接続に失敗しました [{method} {path}]: {e.reason}")


def parse_article(path):
    """HTML ファイルを (meta dict, content str) に分解する。"""
    text = path.read_text(encoding="utf-8")
    meta = {}
    content = text
    stripped = text.lstrip()
    if stripped.startswith("<!--"):
        end = stripped.find("-->")
        if end != -1:
            block = stripped[4:end]
            content = stripped[end + 3:].lstrip("\n")
            for line in block.splitlines():
                line = line.strip()
                if not line or line.lower() == "wp" or ":" not in line:
                    continue
                key, _, value = line.partition(":")
                meta[key.strip().lower()] = value.strip()
    return meta, content


def split_list(value):
    return [v.strip() for v in value.split(",") if v.strip()] if value else []


def resolve_terms(api_base, headers, taxonomy, names, dry_run):
    """カテゴリ/タグ名を ID に解決する。無ければ作成する。"""
    ids = []
    for name in names:
        if dry_run:
            print(f"      [dry-run] {taxonomy}: '{name}' を解決/作成")
            continue
        found = api_request(api_base, headers, f"/{taxonomy}",
                            params={"search": name, "per_page": 100})
        match = next((t for t in (found or []) if t.get("name") == name), None)
        if match:
            ids.append(match["id"])
        else:
            created = api_request(api_base, headers, f"/{taxonomy}",
                                 method="POST", body={"name": name})
            ids.append(created["id"])
            print(f"      {taxonomy} '{name}' を新規作成 (id={created['id']})")
    return ids


def find_existing_post(api_base, headers, slug):
    posts = api_request(api_base, headers, "/posts",
                       params={"slug": slug, "status": "any", "per_page": 1})
    return posts[0] if posts else None


def upload_article(api_base, headers, path, default_status, dry_run):
    meta, content = parse_article(path)
    title = meta.get("title")
    if not title:
        fail(f"{path.name}: メタ情報に title がありません。")
    slug = meta.get("slug") or path.stem
    status = meta.get("status", default_status).lower()
    if status not in VALID_STATUSES:
        fail(f"{path.name}: 不正な status '{status}'（{', '.join(sorted(VALID_STATUSES))} のいずれか）")

    payload = {
        "title": title,
        "slug": slug,
        "status": status,
        "content": content,
    }
    if meta.get("excerpt"):
        payload["excerpt"] = meta["excerpt"]

    cat_names = split_list(meta.get("categories", ""))
    tag_names = split_list(meta.get("tags", ""))
    if cat_names:
        payload["categories"] = resolve_terms(api_base, headers, "categories", cat_names, dry_run)
    if tag_names:
        payload["tags"] = resolve_terms(api_base, headers, "tags", tag_names, dry_run)

    existing = None if dry_run else find_existing_post(api_base, headers, slug)

    if dry_run:
        print(f"  [dry-run] {path.name} -> slug='{slug}', status='{status}', title='{title}'")
        return

    if existing:
        result = api_request(api_base, headers, f"/posts/{existing['id']}",
                            method="POST", body=payload)
        print(f"  更新 ✓ {path.name} -> post {result['id']} ({result['status']}) {result['link']}")
    else:
        result = api_request(api_base, headers, "/posts", method="POST", body=payload)
        print(f"  新規 ✓ {path.name} -> post {result['id']} ({result['status']}) {result['link']}")


def collect_paths(args):
    files = [a for a in args if not a.startswith("-")]
    if files:
        paths = [Path(f) for f in files]
        return [p for p in paths if p.suffix.lower() == ".html" and p.is_file()]
    return sorted(ARTICLES_DIR.glob("*.html"))


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    default_status = os.environ.get("DEFAULT_STATUS", "draft").lower()

    paths = collect_paths(args)
    if not paths:
        print("アップロード対象の HTML 記事が見つかりませんでした。")
        return

    url, headers = (None, None) if dry_run else get_config()
    api_base = f"{url}/wp-json/wp/v2" if url else ""

    print(f"対象記事: {len(paths)} 件（既定ステータス: {default_status}）")
    for path in paths:
        upload_article(api_base, headers, path, default_status, dry_run)
    print("完了しました。")


if __name__ == "__main__":
    main()
