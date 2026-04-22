#!/usr/bin/env python3
"""
Gmail通知スクリプト。
  エラー: python3 scripts/notify_error.py "ステップ名" "詳細メッセージ"
  成功:   python3 scripts/notify_error.py --success "詳細メッセージ"
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
    if not os.environ.get("GMAIL_ADDRESS"):
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
    print(f"エラー通知送信: {step}")
    _send_gmail(f"[SODA] {today} エラー: {step}", body)


def _send_gmail(subject: str, body: str) -> None:
    user = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not user or not password:
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = user
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(user, password)
            s.sendmail(user, user, msg.as_string())
    except Exception as e:
        print(f"メール送信失敗: {e}")


def notify_success(detail: str) -> None:
    today = date.today().strftime("%Y-%m-%d")
    note_url_file = Path(__file__).parent.parent / "logs" / "daily" / f"{today}_note_url.txt"
    note_url = note_url_file.read_text().strip() if note_url_file.exists() else "（未取得）"
    body = f"""SODAパイプラインが正常完了しました。

日付: {today}
note URL: {note_url}

{detail}
"""
    print(f"成功通知送信: {today}")
    _send_gmail(f"[SODA] {today} 完了", body)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--success":
        detail = sys.argv[2] if len(sys.argv) > 2 else ""
        notify_success(detail)
    else:
        step = sys.argv[1] if len(sys.argv) > 1 else "不明なステップ"
        detail = sys.argv[2] if len(sys.argv) > 2 else "詳細不明"
        notify_error(step, detail)
