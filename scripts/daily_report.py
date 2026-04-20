#!/usr/bin/env python3
"""
日次レポートメール（毎日22:00）
各スクリプトの稼働状況・エラー・今日の決定事項をGmailに送信する。
使い方:
  python3 scripts/daily_report.py          # 実行
  python3 scripts/daily_report.py --dry-run  # メール本文だけ表示
"""

import os
import re
import argparse
import smtplib
from email.mime.text import MIMEText
from pathlib import Path
from datetime import date
from dotenv import load_dotenv

SODA_DIR = Path(__file__).parent.parent
load_dotenv(SODA_DIR / ".env")

# 各スクリプトの定義: (表示名, 予定時刻, cronログ, 期待する出力ファイル or None)
SYSTEMS = [
    ("朝パイプライン（note生成・X朝投稿）", "08:07", "logs/cron/{date}_run.log",     None),
    ("全Agent朝会議",                     "07:30", "logs/cron/meeting.log",          "logs/meeting/{date}_meeting.md"),
    ("投稿分析",                           "08:45", "logs/cron/post_analysis.log",    "logs/daily/{date}_post_analysis.md"),
    ("アイデア資産化",                     "09:00", "logs/cron/idea_mining.log",      "logs/ideas/{date}_ideas.md"),
    ("X昼投稿",                            "12:00", "logs/cron/x_noon.log",           None),
    ("CTA改善",                            "18:00", "logs/cron/cta.log",              "logs/daily/{date}_cta.md"),
    ("X夜投稿",                            "20:00", "logs/cron/x_evening.log",        None),
    ("商品メモ",                           "21:00", "logs/cron/product_memo.log",     "logs/daily/{date}_product_memo.md"),
    ("リスト導線確認",                     "21:15", "logs/cron/list_check.log",       "logs/daily/{date}_list_check.md"),
]

WEEKLY_SYSTEMS = [
    ("商品化会議",           "水 20:00", "logs/cron/product_meeting.log"),
    ("リード獲得導線チェック", "金 19:00", "logs/cron/lead_funnel.log"),
    ("週次分析",             "日 21:30", "logs/cron/weekly_cron.log"),
]


def check_log_for_errors(log_path: Path) -> tuple[bool, str]:
    """ログファイルを読んでエラーの有無を返す。(ran_today, error_snippet)"""
    if not log_path.exists():
        return False, "ログファイルなし"
    text = log_path.read_text(errors="replace")
    today_str = str(date.today())
    # 今日の記録があるか（日付文字列またはタイムスタンプで判断）
    ran_today = today_str in text
    # エラー検出
    error_lines = [l.strip() for l in text.splitlines()
                   if any(w in l for w in ["エラー", "Error", "error", "Traceback", "失敗", "exit: 1"])]
    snippet = "\n".join(error_lines[-5:]) if error_lines else ""
    return ran_today, snippet


def extract_section(text: str, header: str, next_header_prefix: str = "## ") -> str:
    """markdownから指定セクションを抜き出す。"""
    start = text.find(header)
    if start == -1:
        return ""
    end = text.find(next_header_prefix, start + len(header))
    block = text[start: end if end != -1 else start + 600]
    return block.strip()


def check_claude_auth() -> tuple[bool, str]:
    """Claude CLIの認証状態を確認する。"""
    import subprocess
    claude = os.path.expanduser("~/.local/bin/claude")
    if not Path(claude).exists():
        return False, "claude CLIが見つかりません"
    result = subprocess.run([claude, "--version"], capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        return False, "claude --version が失敗しました"
    return True, result.stdout.strip()


def collect_today_decisions(today: date) -> dict:
    ds = str(today)
    decisions = {}

    # CTA決定
    cta_file = SODA_DIR / "logs" / "daily" / f"{ds}_cta.md"
    if cta_file.exists():
        t = cta_file.read_text()
        decisions["cta"] = extract_section(t, "## 今日のCTA決定")

    # リスト導線状態
    list_file = SODA_DIR / "logs" / "daily" / f"{ds}_list_check.md"
    if list_file.exists():
        t = list_file.read_text()
        decisions["list_check"] = extract_section(t, "## 総合評価")

    # 会議サマリー
    meeting_file = SODA_DIR / "logs" / "meeting" / f"{ds}_meeting.md"
    if meeting_file.exists():
        t = meeting_file.read_text()
        decisions["meeting"] = extract_section(t, "## 改善アクション")

    # 商品メモ
    memo_file = SODA_DIR / "logs" / "daily" / f"{ds}_product_memo.md"
    if memo_file.exists():
        t = memo_file.read_text()
        decisions["product_memo"] = extract_section(t, "## 商品メモ")

    return decisions


def build_email_body(today: date) -> tuple[str, str]:
    ds = str(today)
    ok_count = 0
    error_count = 0
    not_run_count = 0

    status_rows = []
    error_details = []

    for name, time_str, log_rel, output_rel in SYSTEMS:
        log_path = SODA_DIR / log_rel.replace("{date}", ds)
        ran, err_snippet = check_log_for_errors(log_path)

        # 出力ファイルの存在確認
        output_ok = True
        if output_rel:
            output_path = SODA_DIR / output_rel.replace("{date}", ds)
            output_ok = output_path.exists()

        if not ran:
            icon = "⏳"
            status = "未実行（まだ時間前 or スキップ）"
            not_run_count += 1
        elif err_snippet or not output_ok:
            icon = "❌"
            status = "エラーあり" if err_snippet else "出力ファイルなし"
            error_count += 1
            if err_snippet:
                error_details.append(f"【{name}】\n{err_snippet}")
            if not output_ok and output_rel:
                error_details.append(f"【{name}】出力ファイルが見つかりません: {output_rel.replace('{date}', ds)}")
        else:
            icon = "✅"
            status = "正常"
            ok_count += 1

        status_rows.append(f"  {icon} {time_str}  {name}  — {status}")

    decisions = collect_today_decisions(today)

    claude_ok, claude_msg = check_claude_auth()
    claude_status = f"✅ {claude_msg}" if claude_ok else f"❌ 認証エラー — {claude_msg}"

    lines = [
        f"SODA 日次レポート — {ds}",
        "=" * 50,
        "",
        f"✅ 正常: {ok_count}  ❌ エラー: {error_count}  ⏳ 未実行: {not_run_count}",
        f"Claude CLI: {claude_status}",
        "",
        "■ 稼働状況",
        *status_rows,
        "",
    ]

    if error_details:
        lines += [
            "■ エラー詳細（要対応）",
            *[f"\n{d}" for d in error_details],
            "",
            "対処方法: ログファイルを確認し、スクリプトを手動で再実行してください。",
            f"  python3 scripts/<スクリプト名>.py",
            "",
        ]

    if decisions.get("cta"):
        lines += ["■ 今日のCTA決定", decisions["cta"], ""]

    if decisions.get("meeting"):
        lines += ["■ 今日の改善アクション（会議より）", decisions["meeting"], ""]

    if decisions.get("list_check"):
        lines += ["■ リスト導線状態", decisions["list_check"], ""]

    if decisions.get("product_memo"):
        lines += ["■ 商品メモ", decisions["product_memo"], ""]

    lines += [
        "=" * 50,
        "ログ場所: ~/Desktop/SODA/logs/",
        "手動実行: python3 scripts/<スクリプト名>.py",
    ]

    body = "\n".join(lines)
    subject = f"[SODA] {ds} 日次レポート — ✅{ok_count} ❌{error_count}"
    return subject, body


def send_email(subject: str, body: str) -> None:
    user = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = user

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, password)
        s.sendmail(user, user, msg.as_string())
    print(f"日次レポート送信完了: {subject}")


def main():
    parser = argparse.ArgumentParser(description="SODA 日次レポート")
    parser.add_argument("--dry-run", action="store_true", help="メール本文だけ表示")
    args = parser.parse_args()

    today = date.today()
    subject, body = build_email_body(today)

    if args.dry_run:
        print(f"件名: {subject}\n")
        print(body)
        return

    send_email(subject, body)


if __name__ == "__main__":
    main()
