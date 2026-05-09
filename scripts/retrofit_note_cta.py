#!/usr/bin/env python3
"""
過去の note 記事 (.md) の末尾 CTA を Form 受け取り → X フォロー誘導に書き換える。

処理：
  - forms.gle 系の Form CTA を含む記事 → CTA ブロックを X 誘導に置換
  - CTA がない記事 → ハッシュタグ直前 or 末尾に X 誘導 CTA を挿入

副産物：
  docs/note_cta_retrofit_checklist.md
    note.com 上で手動更新するためのチェックリスト（記事URL + 貼り付け文面）

使い方：
  python3 scripts/retrofit_note_cta.py            # 実行（書き込み）
  python3 scripts/retrofit_note_cta.py --dry-run  # 変更内容を確認のみ
"""

import argparse
import re
import sys
from pathlib import Path

SODA_DIR = Path(__file__).parent.parent
NOTE_DIR = SODA_DIR / "content" / "note"
URL_DIR = SODA_DIR / "logs" / "daily"
CHECKLIST_PATH = SODA_DIR / "docs" / "note_cta_retrofit_checklist.md"

NEW_CTA = """---

**Xでも毎日AIニュースを構造解説しています**

このnoteで取り上げた切り口を、Xでは1日3本（朝・昼・夜）短く更新中。
毎日のAIニュースを「なぜ起きているか」で読めます。

→ フォロー: https://x.com/SODA_LABO"""

HASHTAG_LINE_RE = re.compile(r"^#[^\s#].*(\s#[^\s#]+)*\s*$", re.MULTILINE)


def find_hashtag_line(text: str) -> int | None:
    """末尾付近のハッシュタグ行の開始位置を返す。なければ None。"""
    lines = text.splitlines(keepends=True)
    pos = len(text)
    for line in reversed(lines):
        stripped = line.strip()
        pos -= len(line)
        if not stripped:
            continue
        if stripped.startswith("#") and " " in stripped and all(
            tok.startswith("#") for tok in stripped.split()
        ):
            return pos
        if stripped.startswith("*status:") or stripped.startswith("status:"):
            continue
        return None
    return None


def find_form_cta_block(text: str) -> tuple[int, int] | None:
    """forms.gle を含む CTA ブロック（直前の `---` から `forms.gle/...` の行末まで）を返す。"""
    m = re.search(r"https://forms\.gle/\S+", text)
    if not m:
        return None
    line_end = text.find("\n", m.end())
    if line_end == -1:
        line_end = len(text)
    sep = "\n---\n"
    sep_pos = text.rfind(sep, 0, m.start())
    if sep_pos == -1:
        sep_pos = text.rfind("\n---", 0, m.start())
        if sep_pos == -1:
            return None
    return (sep_pos, line_end)


def transform(text: str) -> tuple[str, str]:
    """
    Returns (new_text, action) where action ∈
      {"replaced_form_cta", "inserted_before_hashtags", "appended", "no_change"}
    """
    block = find_form_cta_block(text)
    if block:
        start, end = block
        new_text = text[:start] + "\n\n" + NEW_CTA + text[end:]
        return new_text, "replaced_form_cta"

    if "https://x.com/SODA_LABO" in text or "x.com/SODA_LABO" in text:
        return text, "no_change"

    hashtag_pos = find_hashtag_line(text)
    if hashtag_pos is not None:
        head = text[:hashtag_pos].rstrip()
        head = re.sub(r"\n+---\s*$", "", head)
        head += "\n"
        new_text = head + "\n" + NEW_CTA + "\n\n" + text[hashtag_pos:]
        return new_text, "inserted_before_hashtags"

    head = text.rstrip()
    head = re.sub(r"\n+---\s*$", "", head)
    new_text = head + "\n\n" + NEW_CTA + "\n"
    return new_text, "appended"


def load_note_url(date_str: str) -> str | None:
    f = URL_DIR / f"{date_str}_note_url.txt"
    if f.exists():
        url = f.read_text(encoding="utf-8").strip()
        return url or None
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = sorted(NOTE_DIR.glob("*.md"))
    if not files:
        print(f"no note files in {NOTE_DIR}")
        return 1

    actions: list[tuple[Path, str, str | None]] = []  # (file, action, url)
    for f in files:
        date_match = re.match(r"(\d{4}-\d{2}-\d{2})_", f.name)
        date_str = date_match.group(1) if date_match else None
        url = load_note_url(date_str) if date_str else None

        text = f.read_text(encoding="utf-8")
        new_text, action = transform(text)
        actions.append((f, action, url))

        if action != "no_change" and not args.dry_run:
            f.write_text(new_text, encoding="utf-8")

        marker = "DRY" if args.dry_run else "✓"
        print(f"  [{marker}] {action:30s}  {f.name}")

    summary = {
        "replaced_form_cta": 0,
        "inserted_before_hashtags": 0,
        "appended": 0,
        "no_change": 0,
    }
    for _, action, _ in actions:
        summary[action] += 1
    print()
    print(f"  total files: {len(files)}")
    for k, v in summary.items():
        print(f"    {k:30s}: {v}")

    if not args.dry_run:
        write_checklist(actions)
        print(f"\n  checklist written: {CHECKLIST_PATH}")

    return 0


def write_checklist(actions: list[tuple[Path, str, str | None]]) -> None:
    lines = [
        "# note.com 公開記事 CTA 後付け チェックリスト",
        "",
        "目的：過去の note 公開記事の末尾 CTA を Form 受け取り → X (@SODA_LABO) フォロー誘導に書き換える。",
        "",
        "ローカル .md は `scripts/retrofit_note_cta.py` で一括更新済み。",
        "**note.com 上の公開記事は手動編集が必要**。下のチェックリストに従って各記事を更新する。",
        "",
        "## 貼り付け文面（全記事共通）",
        "",
        "```",
        NEW_CTA,
        "```",
        "",
        "## 作業手順（1記事あたり）",
        "",
        "1. note.com で該当記事を開く → 編集モード",
        "2. 末尾の `**無料テンプレを受け取る**` ブロック（または末尾本文）を上の文面に置換",
        "3. ハッシュタグはそのまま残す",
        "4. 公開（再公開）",
        "5. このチェックリストの該当行にチェック ✓",
        "",
        "## 対象記事",
        "",
        "| ✓ | 日付 | ファイル | アクション | URL |",
        "|---|------|---------|-----------|-----|",
    ]
    action_label = {
        "replaced_form_cta": "🔁 差替え（Form→X）",
        "inserted_before_hashtags": "➕ 新規追加",
        "appended": "➕ 末尾追加",
        "no_change": "— 変更なし",
    }
    for f, action, url in actions:
        date_match = re.match(r"(\d{4}-\d{2}-\d{2})_", f.name)
        date_str = date_match.group(1) if date_match else "??"
        url_md = f"[開く]({url})" if url else "（URL記録なし）"
        lines.append(f"| ☐ | {date_str} | `{f.name}` | {action_label[action]} | {url_md} |")
    CHECKLIST_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
