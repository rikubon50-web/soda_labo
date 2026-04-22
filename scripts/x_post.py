#!/usr/bin/env python3
"""
X投稿スクリプト（時間差独立投稿）
運用: 朝(--post 1) / 昼(--post 2) / 夜(--post 3) を4時間おきに独立投稿

使い方:
  python3 scripts/x_post.py --today --post 1        # 今日のファイルの1本目
  python3 scripts/x_post.py content/x_posts/... --post 2
  python3 scripts/x_post.py --today --dry-run        # 全3本を確認
"""

import sys
import os
import re
import json
import argparse
from pathlib import Path
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

SODA_DIR = Path(__file__).parent.parent


def find_today_file() -> str | None:
    today = date.today().strftime("%Y-%m-%d")
    files = sorted((SODA_DIR / "content" / "x_posts").glob(f"{today}_*.md"))
    return str(files[0]) if files else None


def _is_hashtag_line(s: str) -> bool:
    """'#AI #副業 #大学生' のようなハッシュタグのみの行を判定する"""
    return bool(re.match(r'^(#[^\s#]+\s*)+$', s))


def parse_posts_and_tags(filepath: str) -> list[tuple[str, str]]:
    """各投稿の (本文, ハッシュタグ行) タプルのリストを返す"""
    text = Path(filepath).read_text(encoding="utf-8")
    blocks = re.split(r"---+|(?=【\d本目】|^#+\s*\d本目)", text, flags=re.MULTILINE)

    results = []
    for block in blocks:
        content_lines = []
        hashtag_str = ""
        for line in block.splitlines():
            s = line.strip()
            if not s or s.startswith("<!--"):
                continue
            if re.match(r"^【\d本目】", s):
                continue
            if _is_hashtag_line(s):
                hashtag_str = s
            elif s.startswith("#"):
                continue  # markdownヘッダーはスキップ
            else:
                content_lines.append(s)
        content = "\n".join(content_lines).strip()
        if content and len(content) >= 10:
            results.append((content, hashtag_str))

    return results[:3]


def parse_posts(filepath: str) -> list[str]:
    return [content for content, _ in parse_posts_and_tags(filepath)]


def build_post_text(content: str, hashtags: str, max_len: int = 140) -> str:
    """本文＋ハッシュタグを結合し、max_len を超える場合は本文を削る"""
    if not hashtags:
        return content[:max_len]
    tag_block = "\n" + hashtags
    available = max_len - len(tag_block)
    body = content[:available] if len(content) > available else content
    return body + tag_block


def save_tweet_id(filepath: str, tweet_id: str, post_number: int, text: str) -> None:
    theme = Path(filepath).stem.split("_", 1)[-1] if "_" in Path(filepath).stem else Path(filepath).stem
    today = date.today().strftime("%Y-%m-%d")
    log_dir = SODA_DIR / "logs" / "tweet_ids"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"{today}.json"
    existing = json.loads(log_file.read_text()) if log_file.exists() else []
    existing.append({
        "tweet_id": str(tweet_id),
        "post_number": post_number,
        "theme": theme,
        "text": text,
        "source_file": str(filepath),
        "posted_at": datetime.now().isoformat(),
    })
    log_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2))


def load_note_url() -> str | None:
    """今日公開されたnote記事URLを読み込む"""
    today = date.today().strftime("%Y-%m-%d")
    url_file = SODA_DIR / "logs" / "daily" / f"{today}_note_url.txt"
    if url_file.exists():
        url = url_file.read_text().strip()
        return url if url else None
    return None


def append_note_url(post: str, note_url: str, max_body: int = 117) -> str:
    """夜投稿にnote URLを追加（X URL=23文字固定、本文をmax_body字以内に収める）"""
    url_line = f"\n\nnote→ {note_url}"
    body = post[:max_body] if len(post) > max_body else post
    return body + url_line


def post_one(filepath: str, post_number: int, dry_run: bool = False) -> None:
    posts_and_tags = parse_posts_and_tags(filepath)

    if post_number < 1 or post_number > len(posts_and_tags):
        print(f"エラー: {post_number}本目が存在しません（全{len(posts_and_tags)}本）")
        sys.exit(1)

    content, hashtags = posts_and_tags[post_number - 1]
    label = ["朝", "昼", "夜"][post_number - 1] if post_number <= 3 else str(post_number)

    post = build_post_text(content, hashtags)

    # 夜投稿（3本目）にnote URLを追加（build_post_text後に付けてURLが切れないようにする）
    if post_number == 3:
        note_url = load_note_url()
        if note_url:
            post = append_note_url(post, note_url)
            print(f"note URL追加: {note_url}")
        else:
            print("note URLファイルなし（URLなしで投稿）")

    if dry_run:
        print(f"=== DRY RUN: {label}投稿（{post_number}本目）({len(post)}文字) ===")
        print(post)
        return

    if len(post) > 280:
        print(f"警告: {post_number}本目が280字超（{len(post)}字）。先頭280字で投稿します。")
        post = post[:280]

    import tweepy
    client = tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )

    response = client.create_tweet(text=post)
    tweet_id = response.data["id"]
    save_tweet_id(filepath, tweet_id, post_number, post)
    print(f"投稿完了: {label}（{post_number}本目）ID: {tweet_id}")


def main():
    parser = argparse.ArgumentParser(description="X投稿スクリプト")
    parser.add_argument("filepath", nargs="?")
    parser.add_argument("--today", action="store_true", help="今日のファイルを自動検索")
    parser.add_argument("--post", type=int, choices=[1, 2, 3], metavar="N",
                        help="投稿する番号（1=朝 / 2=昼 / 3=夜）")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.today:
        filepath = find_today_file()
        if not filepath:
            print("今日のX投稿ファイルが見つかりません")
            sys.exit(1)
    elif args.filepath:
        filepath = args.filepath
    else:
        parser.print_help()
        sys.exit(1)

    if args.dry_run and not args.post:
        # dry-runで番号未指定のときは全3本を表示
        posts_and_tags = parse_posts_and_tags(filepath)
        labels = ["朝", "昼", "夜"]
        for i, ((content, hashtags), label) in enumerate(zip(posts_and_tags, labels), 1):
            combined = build_post_text(content, hashtags)
            print(f"\n=== {label}投稿（{i}本目）({len(combined)}文字) ===")
            print(combined)
        return

    if not args.post:
        print("エラー: --post 1/2/3 を指定してください")
        sys.exit(1)

    post_one(filepath, args.post, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
