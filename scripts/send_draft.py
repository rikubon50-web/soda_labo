#!/usr/bin/env python3
"""
下書きメール送信スクリプト（タイトル・本文を分けてHTML形式で送信）
使い方:
  python3 scripts/send_draft.py content/note/2026-04-19_タイトル.md
  python3 scripts/send_draft.py --today
"""

import smtplib
import os
import sys
import argparse
import markdown
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

HTML_TEMPLATE = """
<html><body style="font-family: sans-serif; max-width: 700px; margin: 0 auto; padding: 20px; color: #333;">

<p style="color:#999; font-size:12px; margin-bottom:24px;">📋 タイトルと本文を別々にコピーしてnoteに貼り付けてください</p>

<div style="background:#f5f5f5; padding:16px; border-radius:8px; margin-bottom:32px;">
  <p style="color:#999; font-size:11px; margin:0 0 8px 0;">▼ タイトル（ここをコピー）</p>
  <p style="font-size:22px; font-weight:bold; margin:0;">{title}</p>
</div>

<div>
  <p style="color:#999; font-size:11px; margin:0 0 8px 0;">▼ 本文（ここをコピー）</p>
  {body}
</div>

</body></html>
"""

def find_today_file(directory: str) -> str | None:
    today = date.today().strftime("%Y-%m-%d")
    files = sorted(Path(directory).glob(f"{today}_*.md"))
    return str(files[0]) if files else None

def send_email(filepath: str) -> None:
    gmail_user = os.environ.get("GMAIL_ADDRESS")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
    to_email   = os.environ.get("GMAIL_ADDRESS")

    if not gmail_user or not gmail_pass:
        print("エラー: GMAIL_ADDRESS と GMAIL_APP_PASSWORD を .env に設定してください")
        sys.exit(1)

    md_content = Path(filepath).read_text(encoding="utf-8")
    lines      = md_content.splitlines()

    # タイトル（# 行）と本文を分離
    title      = next((l.lstrip("# ").strip() for l in lines if l.startswith("# ")), "無題")
    body_lines = [l for l in lines if not l.startswith("# ") or l != f"# {title}"]
    body_md    = "\n".join(body_lines).strip()

    html_body = markdown.markdown(body_md, extensions=["extra", "nl2br"])
    html_full = HTML_TEMPLATE.format(title=title, body=html_body)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[SODA] {title}"
    msg["From"]    = gmail_user
    msg["To"]      = to_email

    msg.attach(MIMEText(body_md,   "plain", "utf-8"))
    msg.attach(MIMEText(html_full, "html",  "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_pass)
        server.sendmail(gmail_user, to_email, msg.as_string())

    print(f"送信完了: {title} → {to_email}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("filepath", nargs="?")
    parser.add_argument("--today", action="store_true")
    args = parser.parse_args()

    if args.today:
        filepath = find_today_file("content/note")
        if not filepath:
            print("今日のnote記事が見つかりません")
            sys.exit(1)
    elif args.filepath:
        filepath = args.filepath
    else:
        parser.print_help()
        sys.exit(1)

    send_email(filepath)

if __name__ == "__main__":
    main()
