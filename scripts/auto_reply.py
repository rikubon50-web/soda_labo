#!/usr/bin/env python3
"""
X自動リプライスクリプト（毎日12:30）
キーワード検索 → Claudeが返信文生成 → CEOが審査 → 承認分のみ送信

使い方:
  python3 scripts/auto_reply.py          # 実行
  python3 scripts/auto_reply.py --dry-run  # プロンプトだけ表示
  python3 scripts/auto_reply.py --send-approved  # 承認済み候補を送信
"""

import os
import json
import argparse
import subprocess
from pathlib import Path
from datetime import date
from dotenv import load_dotenv

SODA_DIR = Path(__file__).parent.parent
load_dotenv(SODA_DIR / ".env")

CLAUDE = os.path.expanduser("~/.local/bin/claude")
PYTHON = "/Users/rikubon50/.pyenv/shims/python3"

def load_keywords() -> list[str]:
    kw_file = SODA_DIR / "config" / "reply_keywords.json"
    if kw_file.exists():
        return json.loads(kw_file.read_text())["keywords"]
    return ["AI 副業 始めた", "note AI 書いた", "AI 発信 挑戦"]

# 1日の最大リプライ数
MAX_REPLIES_PER_DAY = 8

REVIEW_PROMPT = """\
あなたはSODAのCEOです。
X（旧Twitter）での露出拡大のため、キーワード検索で見つけたツイートへの返信候補を審査してください。

## 審査基準（厳格に適用）

**送信OK の条件（全て満たすこと）**
1. 返信がツイート本文の内容と直接関連している
2. 会話として自然（ボット感がない）
3. 宣伝・誘導・リンクが含まれていない
4. 相手にとって何らかの価値がある（共感・情報・視点）
5. 同じ文面や似たパターンの繰り返しでない

**即ボツの条件（1つでも該当したら送信しない）**
- 「AIメディア運営してます」「noteやってます」等の自己紹介混入
- note・フォームURLの埋め込み
- フォロー誘導（「フォローお願いします」等）
- 元ツイートと無関係な内容
- 10文字以下の薄い返信
- 同じような返信が複数候補に含まれている

## 実行手順

1. agents/ceo.md を Read toolで読む
2. 以下の候補リストを審査する
3. logs/daily/{DATE}_reply_candidates.md を Write toolで保存する（全候補の審査結果を記録）
4. 承認した候補のみ logs/daily/{DATE}_reply_approved.json を Write toolで保存する

## 出力フォーマット（logs/daily/{DATE}_reply_candidates.md）

# リプライ候補審査 — {DATE}

## 審査サマリー
- 候補数: X件
- 承認: X件 / ボツ: X件

## 審査結果

### 候補1
**元ツイート**: （元ツイート本文）
**返信案**: （返信文）
**判定**: 承認 / ボツ
**理由**: （1文）

...（全候補分）

## approved.json フォーマット（logs/daily/{DATE}_reply_approved.json）

[
  {
    "tweet_id": "元ツイートID",
    "reply_text": "返信文"
  },
  ...
]

承認が0件の場合は空配列 [] を保存すること。

---

## 審査対象候補

{CANDIDATES}
"""

GENERATE_PROMPT = """\
あなたはSODAのWriterです。
以下のツイートそれぞれに対して、自然で価値のある返信文を生成してください。

## 返信の方針

- **目的**: 露出拡大（良い返信は相手のフォロワーにも表示される）
- **トーン**: 同じ立場で話す感覚。上から目線NG、過剰な謙遜もNG
- **長さ**: 40〜80文字程度
- **禁止事項**:
  - note・フォームURL・リンクを入れない
  - フォロー誘導しない
  - 自己紹介・宣伝を混ぜない
  - 「私もAIメディアやってます」等の売り込み

## 良い返信の型

- 共感型：「わかります、自分も〜で詰まりました」
- 視点追加型：「それ、〜の観点からも面白いと思って」
- 質問型：「〜ってどうやって乗り越えましたか？」
- 補足型：「それに加えて〜も効いた気がします」

## ツイート一覧

{TWEETS}

## 出力形式

各ツイートに対して以下の形式で返信文を出力すること:

Tweet-ID: [ツイートID]
返信文: [返信文]

---
"""


def search_tweets() -> list[dict]:
    """キーワードでツイートを検索して返す"""
    import tweepy

    client = tweepy.Client(
        bearer_token=os.environ["X_BEARER_TOKEN"],
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )

    tweets = []
    seen_ids = set()

    for keyword in load_keywords():
        try:
            resp = client.search_recent_tweets(
                query=f"{keyword} -is:retweet -is:reply lang:ja",
                max_results=10,
                tweet_fields=["id", "text", "author_id", "created_at"],
            )
            if resp.data:
                for t in resp.data:
                    if t.id not in seen_ids:
                        seen_ids.add(t.id)
                        tweets.append({
                            "id": str(t.id),
                            "text": t.text,
                            "keyword": keyword,
                        })
        except Exception as e:
            print(f"検索失敗（{keyword}）: {e}")

    return tweets[:MAX_REPLIES_PER_DAY * 2]


def generate_replies(tweets: list[dict]) -> list[dict]:
    """Claudeで返信文を生成する"""
    tweets_text = "\n\n".join(
        f"Tweet-ID: {t['id']}\n検索キーワード: {t['keyword']}\nツイート内容: {t['text']}"
        for t in tweets
    )
    prompt = GENERATE_PROMPT.replace("{TWEETS}", tweets_text)

    result = subprocess.run(
        [CLAUDE, "-p", "--dangerously-skip-permissions", "--allowedTools", "Read"],
        input=prompt,
        cwd=str(SODA_DIR),
        capture_output=True,
        text=True,
    )

    # 返信文をパース
    replies = {}
    current_id = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("Tweet-ID:"):
            current_id = line.replace("Tweet-ID:", "").strip()
        elif line.startswith("返信文:") and current_id:
            replies[current_id] = line.replace("返信文:", "").strip()
            current_id = None

    # ツイートと返信文をマージ
    candidates = []
    for t in tweets:
        if t["id"] in replies:
            candidates.append({
                "tweet_id": t["id"],
                "tweet_text": t["text"],
                "reply_text": replies[t["id"]],
            })

    return candidates


def review_with_ceo(candidates: list[dict], today: date) -> list[dict]:
    """CEOに候補を審査させる"""
    ds = str(today)

    candidates_text = ""
    for i, c in enumerate(candidates, 1):
        candidates_text += f"""
### 候補{i}
Tweet-ID: {c['tweet_id']}
元ツイート: {c['tweet_text']}
返信案: {c['reply_text']}

"""

    prompt = REVIEW_PROMPT.replace("{DATE}", ds).replace("{CANDIDATES}", candidates_text)

    result = subprocess.run(
        [CLAUDE, "-p", "--dangerously-skip-permissions", "--allowedTools", "Read,Write"],
        input=prompt,
        cwd=str(SODA_DIR),
        capture_output=True,
        text=True,
    )

    # 承認済みJSONを読み込む
    approved_file = SODA_DIR / "logs" / "daily" / f"{ds}_reply_approved.json"
    if approved_file.exists():
        return json.loads(approved_file.read_text())
    return []


def send_replies(approved: list[dict]) -> None:
    """承認済みリプライを送信する"""
    import tweepy

    client = tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )

    sent = 0
    for item in approved[:MAX_REPLIES_PER_DAY]:
        try:
            resp = client.create_tweet(
                text=item["reply_text"],
                in_reply_to_tweet_id=item["tweet_id"],
            )
            print(f"送信完了: {item['reply_text'][:40]}... → ID: {resp.data['id']}")
            sent += 1
        except Exception as e:
            print(f"送信失敗: {e}")

    print(f"リプライ送信完了: {sent}件")


def main():
    parser = argparse.ArgumentParser(description="X自動リプライスクリプト")
    parser.add_argument("--dry-run", action="store_true", help="プロンプトだけ表示")
    parser.add_argument("--send-approved", action="store_true", help="承認済み候補を送信")
    args = parser.parse_args()

    today = date.today()
    ds = str(today)
    log_file = SODA_DIR / "logs" / "cron" / f"{ds}_auto_reply.log"

    # 送信モード
    if args.send_approved:
        approved_file = SODA_DIR / "logs" / "daily" / f"{ds}_reply_approved.json"
        if not approved_file.exists():
            print("承認済みファイルが見つかりません")
            return
        approved = json.loads(approved_file.read_text())
        if not approved:
            print("承認済みリプライなし")
            return
        send_replies(approved)
        return

    print(f"[{today}] ツイート検索中...")
    tweets = search_tweets()
    if not tweets:
        print("該当ツイートなし")
        log_file.write_text("該当ツイートなし\n")
        return

    print(f"{len(tweets)}件取得。返信文生成中...")
    if args.dry_run:
        for t in tweets:
            print(f"  [{t['keyword']}] {t['text'][:60]}...")
        return

    candidates = generate_replies(tweets)
    if not candidates:
        print("返信文の生成失敗")
        log_file.write_text("返信文生成失敗\n")
        return

    print(f"{len(candidates)}件の候補をCEOが審査中...")
    approved = review_with_ceo(candidates, today)

    log_file.write_text(
        f"候補数: {len(candidates)}\n承認数: {len(approved)}\n"
    )

    if not approved:
        print("承認されたリプライなし（今日は送信しない）")
        return

    print(f"{len(approved)}件承認。送信中...")
    send_replies(approved)


if __name__ == "__main__":
    main()
