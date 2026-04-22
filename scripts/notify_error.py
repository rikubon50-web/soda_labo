#!/usr/bin/env python3
"""
エラー通知スクリプト
エラーを logs/errors/{today}_errors.log に記録し、Gmailで通知する。
リトライ済みの本当の失敗のみ呼ばれる想定。
使い方: python3 scripts/notify_error.py "ステップ名" "詳細メッセージ"
"""
import os
import smtplib
import sys
from datetime import date, datetime
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


def notify_error(step: str, detail: str) -> None:
    today = date.today().strftime("%Y-%m-%d")
    ts = datetime.now().strftime("%H:%M:%S")

    # ログファイルに記録
    log_dir = Path(__file__).parent.parent / "logs" / "errors"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{today}_errors.log"
    with log_file.open("a", encoding="utf-8", errors="replace") as f:
        f.write(f"[{ts}] {step}: {detail}\n")

    # Gmail通知
    user = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not user or not password:
        print(f"エラー記録（メール未設定）: {step}")
        return

    log_path = Path(__file__).parent.parent / "logs" / "cron" / f"{today}_run.log"
    body = f"""SODAパイプラインでエラーが発生しました。

ステップ: {step}
日付: {today}

詳細:
{detail}

ログファイル: {log_path}
"""
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"[SODA] {today} エラー: {step}"
    msg["From"] = user
    msg["To"] = user

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(user, password)
            s.sendmail(user, user, msg.as_string())
        print(f"エラー通知送信: {step}")
    except Exception as e:
        print(f"エラー記録（メール送信失敗: {e}）: {step}")


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "不明なステップ"
    detail = sys.argv[2] if len(sys.argv) > 2 else "詳細不明"
    notify_error(step, detail)
