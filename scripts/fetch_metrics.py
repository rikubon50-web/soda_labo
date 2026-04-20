#!/usr/bin/env python3
"""
X投稿のメトリクスを取得してログに保存するスクリプト
使い方:
  python3 scripts/fetch_metrics.py          # 過去7日分を取得
  python3 scripts/fetch_metrics.py --days 3 # 過去3日分
"""

import os
import json
import argparse
from pathlib import Path
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

SODA_DIR = Path(__file__).parent.parent


def load_tweet_ids(days: int) -> list[dict]:
    """過去N日分のツイートIDレコードを読み込む"""
    records = []
    for i in range(days):
        target = date.today() - timedelta(days=i)
        log_file = SODA_DIR / "logs" / "tweet_ids" / f"{target}.json"
        if log_file.exists():
            records.extend(json.loads(log_file.read_text()))
    return records


def fetch_and_save(days: int) -> None:
    records = load_tweet_ids(days)
    if not records:
        print(f"過去{days}日分のツイートIDが見つかりません")
        return

    import tweepy

    client = tweepy.Client(
        bearer_token=os.environ["X_BEARER_TOKEN"],
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )

    metrics_by_date: dict[str, list] = {}

    for record in records:
        tweet_id = record["tweet_id"]
        post_date = record["posted_at"][:10]

        try:
            response = client.get_tweet(
                tweet_id,
                tweet_fields=["public_metrics", "created_at"],
            )
            if not response.data:
                continue

            metrics = response.data.public_metrics or {}
            entry = {
                **record,
                "metrics": {
                    "impressions":  metrics.get("impression_count", 0),
                    "likes":        metrics.get("like_count", 0),
                    "retweets":     metrics.get("retweet_count", 0),
                    "replies":      metrics.get("reply_count", 0),
                    "bookmarks":    metrics.get("bookmark_count", 0),
                },
            }
            metrics_by_date.setdefault(post_date, []).append(entry)
            print(f"取得完了: {record['theme']} {record['post_number']}本目 "
                  f"| いいね{entry['metrics']['likes']} "
                  f"/ RT{entry['metrics']['retweets']} "
                  f"/ IMP{entry['metrics']['impressions']}")

        except Exception as e:
            # APIアクセス制限やフリープランではインプレッションが取れない場合がある
            print(f"警告: ツイートID {tweet_id} の取得失敗 → {e}")
            entry = {**record, "metrics": None, "error": str(e)}
            metrics_by_date.setdefault(post_date, []).append(entry)

    # 日付ごとにメトリクスファイルを保存
    metrics_dir = SODA_DIR / "logs" / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    for post_date, entries in metrics_by_date.items():
        out_file = metrics_dir / f"{post_date}.json"
        out_file.write_text(json.dumps(entries, ensure_ascii=False, indent=2))
        print(f"保存: {out_file}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    fetch_and_save(args.days)


if __name__ == "__main__":
    main()
