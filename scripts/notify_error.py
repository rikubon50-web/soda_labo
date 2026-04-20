#!/usr/bin/env python3
"""
エラー通知スクリプト
使い方: python3 scripts/notify_error.py "ステップ名" "詳細メッセージ"
"""
import sys
import smtplib
import os
from email.mime.text import MIMEText
from dotenv import load_dotenv
from pathlib import Path
from datetime import date

load_dotenv(Path(__file__).parent.parent / ".env")

def send_error_notification(step: str, detail: str) -> None:
    user = os.environ["GMAIL_ADDRESS"]
    today = date.today().strftime("%Y-%m-%d")
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

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, os.environ["GMAIL_APP_PASSWORD"])
        s.sendmail(user, user, msg.as_string())
    print(f"エラー通知送信: {step}")

if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "不明なステップ"
    detail = sys.argv[2] if len(sys.argv) > 2 else "詳細不明"
    send_error_notification(step, detail)
